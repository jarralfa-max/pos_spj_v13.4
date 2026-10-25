"""Credenciales de estación para la API central de sincronización (Slice 4).

Cada estación (caja, PC de oficina) tiene su PROPIA credencial: un secreto
aleatorio de 256 bits que se entrega UNA vez al darla de alta y del que el
servidor sólo guarda la huella SHA-256. Por ser aleatorio y largo, no necesita
un hash lento (a diferencia de una contraseña humana); la comparación es en
tiempo constante.

Nunca hay una clave compartida entre estaciones ni una credencial de
administrador en el cliente: dar de baja una estación (o perderla) no expone a
las demás.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

#: Prefijo para reconocer el secreto en un archivo de configuración o un log.
SECRET_PREFIX = "spjst_"


def issue_station_secret() -> tuple[str, str]:
    """(secreto para la estación, huella para el servidor)."""
    secreto = SECRET_PREFIX + secrets.token_urlsafe(32)
    return secreto, station_secret_hash(secreto)


def station_secret_hash(secret: str) -> str:
    return hashlib.sha256(str(secret).encode("utf-8")).hexdigest()


def verify_station_secret(secret: str | None, stored_hash: str | None) -> bool:
    if not secret or not stored_hash:
        return False
    return hmac.compare_digest(station_secret_hash(secret), str(stored_hash))


__all__ = ["SECRET_PREFIX", "issue_station_secret", "station_secret_hash",
           "verify_station_secret"]
