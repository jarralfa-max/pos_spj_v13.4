
# core/security/crypto.py — SPJ POS v10
"""
Encriptacion de campos sensibles en BD (RFC, datos bancarios, API keys).
Usa Fernet (AES-128-CBC + HMAC) si cryptography esta instalado.
Fallback: XOR con clave derivada (proteccion basica).
"""
from __future__ import annotations
import base64, os, logging
from core.db.connection import get_connection

logger = logging.getLogger("spj.crypto")


def _get_or_create_key(conn) -> bytes:
    try:
        row = conn.execute(
            "SELECT valor FROM configuraciones WHERE clave='crypto_key_b64'"
        ).fetchone()
        if row:
            return base64.urlsafe_b64decode(row[0].encode())
    except Exception:
        pass
    key = os.urandom(32)
    b64 = base64.urlsafe_b64encode(key).decode()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO configuraciones(clave,valor) VALUES('crypto_key_b64',?)",
            (b64,))
        conn.commit()
    except Exception:
        pass
    logger.info("Nueva clave de encriptacion generada")
    return key


class FieldEncryptor:
    def __init__(self, conn=None):
        self.conn    = conn or get_connection()
        self._key    = _get_or_create_key(self.conn)
        self._fernet = None
        try:
            from cryptography.fernet import Fernet
            fernet_key   = base64.urlsafe_b64encode(self._key)
            self._fernet = Fernet(fernet_key)
        except ImportError:
            logger.warning("cryptography no instalada — fallback XOR")

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            return plaintext
        if self._fernet:
            return "ENC:" + self._fernet.encrypt(plaintext.encode()).decode()
        key_cycle = (self._key * ((len(plaintext) // 32) + 1))[:len(plaintext)]
        xored = bytes(a ^ b for a, b in zip(plaintext.encode(), key_cycle))
        return "XOR:" + base64.b64encode(xored).decode()

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext:
            return ciphertext
        if ciphertext.startswith("ENC:") and self._fernet:
            try:
                return self._fernet.decrypt(ciphertext[4:].encode()).decode()
            except Exception as e:
                logger.error("decrypt error: %s", e)
                return ciphertext
        if ciphertext.startswith("XOR:"):
            raw = base64.b64decode(ciphertext[4:])
            key_cycle = (self._key * ((len(raw) // 32) + 1))[:len(raw)]
            try:
                return bytes(a ^ b for a, b in zip(raw, key_cycle)).decode()
            except Exception:
                return ciphertext
        return ciphertext

    def is_encrypted(self, value: str) -> bool:
        return isinstance(value, str) and (
            value.startswith("ENC:") or value.startswith("XOR:"))


SENSITIVE_FIELDS = {
    "clientes":    ["rfc", "email", "telefono"],
    "proveedores": ["rfc", "email", "telefono", "cuenta_bancaria"],
    "empleados":   ["rfc", "numero_seguro_social", "cuenta_bancaria"],
}

_encryptor: "FieldEncryptor | None" = None


def get_encryptor(conn=None) -> FieldEncryptor:
    global _encryptor
    if _encryptor is None:
        _encryptor = FieldEncryptor(conn or get_connection())
    return _encryptor


def encrypt_record(tabla: str, record: dict, conn=None) -> dict:
    fields = SENSITIVE_FIELDS.get(tabla, [])
    if not fields:
        return record
    enc    = get_encryptor(conn)
    result = dict(record)
    for f in fields:
        if f in result and result[f] and not enc.is_encrypted(str(result[f])):
            result[f] = enc.encrypt(str(result[f]))
    return result


def decrypt_record(tabla: str, record: dict, conn=None) -> dict:
    fields = SENSITIVE_FIELDS.get(tabla, [])
    if not fields:
        return record
    enc    = get_encryptor(conn)
    result = dict(record)
    for f in fields:
        if f in result and result[f] and enc.is_encrypted(str(result[f])):
            result[f] = enc.decrypt(str(result[f]))
    return result
