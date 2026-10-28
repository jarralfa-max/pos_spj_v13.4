"""Firma de solicitudes con la llave del equipo (auditoría enterprise, Fase 4;
decisión D3).

Cada estación genera su par Ed25519 EN EL EQUIPO; la llave privada nunca sale de
él (se guarda en el almacén de secretos del sistema, protegido con DPAPI en
Windows) y el servidor central sólo conoce la pública. Cada solicitud lleva:

    X-SPJ-Station-Id   id UUIDv7 de la estación
    X-SPJ-Timestamp    segundos UNIX (entero)
    X-SPJ-Nonce        UUID aleatorio por solicitud
    X-SPJ-Signature    Ed25519 (base64) de la cadena canónica

Cadena canónica (una línea por campo, sin espacios extra)::

    SPJ-DEVICE-REQUEST/1
    <MÉTODO>
    <ruta sin dominio, con query>
    <timestamp>
    <nonce>
    <id de estación>
    <sha256 hex del cuerpo>

Firmar el id de estación impide reutilizar una firma con otra identidad; firmar
la huella del cuerpo impide alterar el lote; timestamp + nonce acotan la
repetición (ventana de `MAX_SKEW_SECONDS`, nonce de un solo uso en esa ventana).
Ni la MAC, ni el nombre del equipo ni su número de serie autentican nada.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import threading
import time
import uuid
from collections import OrderedDict

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

ALGORITHM = "ed25519"
SCHEME = "SPJ-DEVICE-REQUEST/1"
MAX_SKEW_SECONDS = 300

H_STATION = "X-SPJ-Station-Id"
H_TIMESTAMP = "X-SPJ-Timestamp"
H_NONCE = "X-SPJ-Nonce"
H_SIGNATURE = "X-SPJ-Signature"


class DeviceSignatureError(ValueError):
    """Firma ausente, mal formada, vencida, repetida o inválida."""


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: str) -> bytes:
    try:
        return base64.b64decode(str(text).encode("ascii"), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DeviceSignatureError("Base64 inválido") from exc


def generate_device_keypair() -> tuple[str, str]:
    """(llave privada, llave pública), ambas Ed25519 crudas en base64."""
    privada = Ed25519PrivateKey.generate()
    crudo_priv = privada.private_bytes(serialization.Encoding.Raw,
                                       serialization.PrivateFormat.Raw,
                                       serialization.NoEncryption())
    crudo_pub = privada.public_key().public_bytes(serialization.Encoding.Raw,
                                                  serialization.PublicFormat.Raw)
    return _b64(crudo_priv), _b64(crudo_pub)


def public_key_from_private(private_b64: str) -> str:
    privada = Ed25519PrivateKey.from_private_bytes(_unb64(private_b64))
    return _b64(privada.public_key().public_bytes(serialization.Encoding.Raw,
                                                  serialization.PublicFormat.Raw))


def validate_public_key(public_b64: str) -> str:
    crudo = _unb64(public_b64)
    if len(crudo) != 32:
        raise DeviceSignatureError("La llave pública Ed25519 debe tener 32 bytes")
    Ed25519PublicKey.from_public_bytes(crudo)
    return _b64(crudo)


def canonical_request(*, method: str, path: str, timestamp: str, nonce: str,
                      station_id: str, body: bytes) -> bytes:
    return "\n".join((SCHEME, method.upper(), path, str(timestamp), nonce, station_id,
                      hashlib.sha256(body or b"").hexdigest())).encode("utf-8")


def sign_request(private_b64: str, *, method: str, path: str, station_id: str,
                 body: bytes, now: float | None = None) -> dict[str, str]:
    """Encabezados firmados para una solicitud."""
    marca = str(int(time.time() if now is None else now))
    nonce = str(uuid.uuid4())
    privada = Ed25519PrivateKey.from_private_bytes(_unb64(private_b64))
    firma = privada.sign(canonical_request(method=method, path=path, timestamp=marca,
                                           nonce=nonce, station_id=station_id, body=body))
    return {H_STATION: station_id, H_TIMESTAMP: marca, H_NONCE: nonce,
            H_SIGNATURE: _b64(firma)}


class NonceCache:
    """Nonces vistos dentro de la ventana, por proceso. Una firma capturada no se
    puede volver a presentar mientras sea válida por tiempo."""

    def __init__(self, ttl_seconds: int = MAX_SKEW_SECONDS * 2, max_items: int = 100_000):
        self._ttl = ttl_seconds
        self._max = max_items
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._lock = threading.Lock()

    def add(self, key: str, now: float) -> bool:
        with self._lock:
            while self._seen:
                primero, cuando = next(iter(self._seen.items()))
                if now - cuando <= self._ttl and len(self._seen) < self._max:
                    break
                self._seen.popitem(last=False)
            if key in self._seen:
                return False
            self._seen[key] = now
            return True


def verify_request(public_b64: str, *, method: str, path: str, headers, body: bytes,
                   nonces: NonceCache | None = None, now: float | None = None) -> str:
    """Devuelve el id de estación firmado o lanza `DeviceSignatureError`."""
    def h(nombre):
        valor = headers.get(nombre) or headers.get(nombre.lower())
        if not valor:
            raise DeviceSignatureError(f"Falta {nombre}")
        return str(valor)

    estacion, marca, nonce, firma = h(H_STATION), h(H_TIMESTAMP), h(H_NONCE), h(H_SIGNATURE)
    if not marca.isdigit():
        raise DeviceSignatureError("Marca de tiempo inválida")
    ahora = time.time() if now is None else now
    if abs(ahora - int(marca)) > MAX_SKEW_SECONDS:
        raise DeviceSignatureError("La firma venció (reloj del equipo desfasado o repetición)")
    try:
        Ed25519PublicKey.from_public_bytes(_unb64(public_b64)).verify(
            _unb64(firma), canonical_request(method=method, path=path, timestamp=marca,
                                             nonce=nonce, station_id=estacion, body=body))
    except (InvalidSignature, ValueError) as exc:
        raise DeviceSignatureError("Firma inválida") from exc
    if nonces is not None and not nonces.add(f"{estacion}:{nonce}", ahora):
        raise DeviceSignatureError("Solicitud repetida")
    return estacion


__all__ = ["ALGORITHM", "DeviceSignatureError", "H_NONCE", "H_SIGNATURE", "H_STATION",
           "H_TIMESTAMP", "MAX_SKEW_SECONDS", "NonceCache", "canonical_request",
           "generate_device_keypair", "public_key_from_private", "sign_request",
           "validate_public_key", "verify_request"]
