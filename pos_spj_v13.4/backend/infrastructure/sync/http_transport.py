"""Transporte HTTPS de la estación hacia el servidor central (Slice 4).

Implementa `ReplicationTransport` del motor de replicación: entrega un lote a
`POST {base}/api/v1/sync/events` y devuelve los acuses. Cualquier falla de red,
de servidor (5xx), de cupo (429) o de credencial (401/403) se convierte en
`TransportUnavailable`: el motor deja TODO el lote en reintento, sin perder nada,
y el POS sigue vendiendo.

* Exige HTTPS. HTTP sólo se permite contra `localhost` y de forma explícita
  (`allow_insecure_localhost=True`, para desarrollo y pruebas).
* Verifica el certificado del servidor (TLS de Caddy, ADR-001).
* El secreto de la estación viaja sólo en el encabezado `Authorization`.
"""

from __future__ import annotations

from typing import Sequence
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
    def __init__(self, base_url: str, *, station_id: str, secret: str,
                 timeout_s: float = 15.0, client=None,
                 allow_insecure_localhost: bool = False) -> None:
        partes = urlsplit(base_url)
        if partes.scheme != "https" and not (
                allow_insecure_localhost and partes.scheme == "http"
                and partes.hostname in _LOCAL):
            raise ValueError("El servidor central se contacta por HTTPS")
        if not secret:
            raise ValueError("La estación no tiene credencial configurada")
        self._url = base_url.rstrip("/") + "/api/v1/sync/events"
        self._station = station_id
        self._secret = secret
        self._timeout = timeout_s
        self._client = client

    def push(self, *, station_id: str, branch_id: str,
             envelopes: Sequence[ReplicationEnvelope]) -> Sequence[ReplicationAck]:
        import httpx

        if station_id != self._station:
            raise TransportUnavailable("La estación del motor no coincide con su credencial")
        cuerpo = {"envelopes": [s.to_dict() for s in envelopes]}
        encabezados = {"X-SPJ-Station-Id": self._station,
                       "Authorization": f"Bearer {self._secret}",
                       "X-Request-ID": new_uuid()}
        try:
            if self._client is not None:
                respuesta = self._client.post(self._url, json=cuerpo, headers=encabezados,
                                              timeout=self._timeout)
            else:
                with httpx.Client(timeout=self._timeout, verify=True) as cliente:
                    respuesta = cliente.post(self._url, json=cuerpo, headers=encabezados)
        except httpx.HTTPError as exc:
            raise TransportUnavailable(f"Sin conexión con el servidor central: {exc}") from exc
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
