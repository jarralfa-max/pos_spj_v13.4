"""Derivación HMAC del token público de las tarjetas (LOY-29, §32, §51).

token = base64url(HMAC-SHA256(secreto, "<token_id>:<versión>"))[:32]

* Aleatorio y no predecible para quien no tiene el secreto (256 bits de HMAC).
* Determinista para la instalación: reimprimir produce el MISMO QR sin haberlo
  guardado nunca.
* Revocable y rotable: rotar crea otro registro de token (otro id, otro token).

DÓNDE VIVE EL SECRETO: en `loyalty_card_secrets`, dentro de la misma base. Se
descartó el almacén de secretos del sistema operativo a propósito: es por
máquina, y una tarjeta emitida en una sucursal debe poder reimprimirse en otra
con el mismo QR (la base es la que se sincroniza). Es el mismo criterio que
Logística aplica a sus QR. Lo que se protege con la huella es que exportar o
sincronizar las tablas de tarjetas no revele ningún token.

El secreto se crea la primera vez que se emite un token, dentro de la
transacción de quien lo pide (nunca hace commit por su cuenta).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timezone

SECRET_NAME = "qr_token_secret"
_TOKEN_LENGTH = 32


class HmacCardTokenCodec:
    def __init__(self, secret: bytes) -> None:
        if len(secret) < 32:
            raise ValueError("El secreto de QR de tarjetas debe tener al menos 32 bytes")
        self._secret = secret

    def derive(self, token_id: str, version: int) -> str:
        firma = hmac.new(self._secret, f"{token_id}:{int(version)}".encode("utf-8"),
                         hashlib.sha256).digest()
        return base64.urlsafe_b64encode(firma).decode("ascii").rstrip("=")[:_TOKEN_LENGTH]


def card_token_secret(connection, *, create: bool = True) -> bytes | None:
    fila = connection.execute(
        "SELECT value FROM loyalty_card_secrets WHERE id = ?", (SECRET_NAME,)).fetchone()
    if fila and fila[0]:
        return bytes.fromhex(str(fila[0]))
    if not create:
        return None
    valor = secrets.token_hex(32)
    connection.execute(
        "INSERT INTO loyalty_card_secrets (id, value, created_at) VALUES (?, ?, ?)",
        (SECRET_NAME, valor, datetime.now(timezone.utc).isoformat(timespec="seconds")))
    return bytes.fromhex(valor)


def card_token_codec_for(connection) -> HmacCardTokenCodec:
    return HmacCardTokenCodec(card_token_secret(connection))


__all__ = ["HmacCardTokenCodec", "SECRET_NAME", "card_token_codec_for", "card_token_secret"]
