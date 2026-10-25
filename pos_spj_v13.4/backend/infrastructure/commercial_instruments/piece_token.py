"""Derivación del código de una pieza de lote (mismo esquema que el QR de las
tarjetas de fidelidad, `backend/infrastructure/loyalty_cards/token_codec.py`).

código = prefijo + Base32(HMAC-SHA256(secreto, "<pieza>:<versión>"))[:16]

* No predecible sin el secreto (80 bits del HMAC).
* Determinista: reimprimir una pieza produce el MISMO código sin guardarlo.
* Revocable: subir la versión de la pieza da otro código; el anterior deja de
  resolver.

El secreto vive en `commercial_instrument_secrets` (dentro de la base, por la
misma razón que el de tarjetas: una pieza emitida en una sucursal debe poder
reimprimirse en otra). Se crea la primera vez, dentro de la transacción de quien
lo pide (nunca confirma por su cuenta).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from backend.domain.commercial_instruments.value_objects.piece_code import PIECE_TOKEN_LENGTH

SECRET_NAME = "piece_token_secret"


def piece_token_secret(connection, *, create: bool = True) -> bytes | None:
    fila = connection.execute(
        "SELECT value FROM commercial_instrument_secrets WHERE id = ?", (SECRET_NAME,)).fetchone()
    if fila and fila[0]:
        return bytes.fromhex(str(fila[0]))
    if not create:
        return None
    valor = secrets.token_hex(32)
    connection.execute(
        "INSERT INTO commercial_instrument_secrets (id, value, created_at) VALUES (?, ?, ?)",
        (SECRET_NAME, valor, datetime.now(timezone.utc).isoformat(timespec="seconds")))
    return bytes.fromhex(valor)


class PieceCodeCodec:
    def __init__(self, secret: bytes) -> None:
        if len(secret) < 32:
            raise ValueError("El secreto de las piezas debe tener al menos 32 bytes")
        self._secret = secret

    def derive(self, *, prefix: str, item_id: str, version: int) -> str:
        """Forma canónica (`VAL` + 16 caracteres Base32)."""
        firma = hmac.new(self._secret, f"{item_id}:{int(version)}".encode("utf-8"),
                         hashlib.sha256).digest()
        cuerpo = base64.b32encode(firma).decode("ascii").rstrip("=")[:PIECE_TOKEN_LENGTH]
        return f"{prefix}{cuerpo}"


def piece_codec_for(connection) -> PieceCodeCodec:
    return PieceCodeCodec(piece_token_secret(connection))


__all__ = ["PieceCodeCodec", "SECRET_NAME", "piece_codec_for", "piece_token_secret"]
