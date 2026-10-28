"""Transporte HTTPS de la estación hacia el servidor central (Slice 4).

Implementa `ReplicationTransport` del motor de replicación: entrega un lote a
`POST {base}/api/v1/sync/events` y devuelve los acuses. Cualquier falla de red,
de servidor (5xx), de cupo (429) o de credencial (401/403) se convierte en
`TransportUnavailable`: el motor deja TODO el lote en reintento, sin perder nada,
y el POS sigue vendiendo.

* Exige HTTPS. HTTP sólo se permite contra `localhost` y de forma explícita
  (`allow_insecure_localhost=True`, para desarrollo y pruebas).
* Verifica el certificado del servidor (TLS de Caddy, ADR-001).
* Credencial: la llave Ed25519 del equipo (auditoría enterprise, Fase 4): cada lote
  va FIRMADO y la llave privada nunca viaja. En transición se acepta el secreto
  del Slice 4, que viaja sólo en el encabezado `Authorization`.
* Si el central responde que el equipo está suspendido o dado de baja
  (`X-SPJ-Error-Code`), se avisa a `on_access_denied` para que la estación lo
  registre; el lote queda en reintento como cualquier otra falla.
* El proxy delante del central no debe reescribir la ruta: se firma la ruta.
"""

from __future__ import annotations

import json
from typing import Callable, Sequence
from urllib.parse import urlsplit

from backend.application.sync.replication_outbox import TransportUnavailable
from backend.shared.ids import new_uuid
from backend.shared.sync.replication_envelope import (
    EnvelopeError,
    ReplicationAck,
    ReplicationEnvelope,
)

_LOCAL = {"localhost", "127.0.0.1", "::1", "testserver"}


class HttpReplicationTransport:
    def __init__(self, base_url: str, *, station_id: str, secret: str | None = None,
                 private_key: str | None = None, timeout_s: float = 15.0, client=None,
                 allow_insecure_localhost: bool = False,
                 on_access_denied: Callable[[str], None] | None = None) -> None:
        partes = urlsplit(base_url)
        if partes.scheme != "https" and not (
                allow_insecure_localhost and partes.scheme == "http"
                and partes.hostname in _LOCAL):
            raise ValueError("El servidor central se contacta por HTTPS")
        if not secret and not private_key:
            raise ValueError("La estación no tiene credencial configurada")
        self._url = base_url.rstrip("/") + "/api/v1/sync/events"
        self._path = urlsplit(self._url).path
        self._station = station_id
        self._secret = secret
        self._private_key = private_key
        self._on_denied = on_access_denied
        self._timeout = timeout_s
        self._client = client

    def push(self, *, station_id: str, branch_id: str,
             envelopes: Sequence[ReplicationEnvelope]) -> Sequence[ReplicationAck]:
        import httpx

        if station_id != self._station:
            raise TransportUnavailable("La estación del motor no coincide con su credencial")
        crudo = json.dumps({"envelopes": [s.to_dict() for s in envelopes]},
                           separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        encabezados = {"X-SPJ-Station-Id": self._station, "X-Request-ID": new_uuid(),
                       "Content-Type": "application/json"}
        if self._private_key:
            from backend.shared.security.device_signature import sign_request
            encabezados.update(sign_request(self._private_key, method="POST", path=self._path,
                                            station_id=self._station, body=crudo))
        else:
            encabezados["Authorization"] = f"Bearer {self._secret}"
        try:
            if self._client is not None:
                respuesta = self._client.post(self._url, content=crudo, headers=encabezados,
                                              timeout=self._timeout)
            else:
                with httpx.Client(timeout=self._timeout, verify=True) as cliente:
                    respuesta = cliente.post(self._url, content=crudo, headers=encabezados)
        except httpx.HTTPError as exc:
            raise TransportUnavailable(f"Sin conexión con el servidor central: {exc}") from exc
        codigo = respuesta.headers.get("X-SPJ-Error-Code")
        if respuesta.status_code == 403 and codigo and self._on_denied is not None:
            self._on_denied(codigo)
        if respuesta.status_code in (401, 403):
            raise TransportUnavailable(
                f"El servidor central rechazó la credencial de la estación ({respuesta.status_code})")
        if respuesta.status_code == 429 or respuesta.status_code >= 500:
            raise TransportUnavailable(f"Servidor central ocupado ({respuesta.status_code})")
        if respuesta.status_code != 200:
            raise TransportUnavailable(
                f"Respuesta inesperada del servidor central ({respuesta.status_code})")
        try:
            return [ReplicationAck.from_dict(a) for a in respuesta.json()["acks"]]
        except (KeyError, ValueError, TypeError, EnvelopeError) as exc:
            raise TransportUnavailable(f"Acuses ilegibles del servidor central: {exc}") from exc


__all__ = ["HttpReplicationTransport"]
