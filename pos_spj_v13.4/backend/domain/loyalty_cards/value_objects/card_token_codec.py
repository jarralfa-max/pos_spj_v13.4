"""Token público del QR de una tarjeta: cómo se deriva y cómo se guarda (§32).

El QR lleva un token aleatorio y no predecible, nunca un id interno. Lo que se
GUARDA es su huella (`hash_public_token`) y un prefijo corto para soporte; el
token completo no vive en ninguna tabla.

Para poder reimprimir el MISMO QR sin guardarlo (§51), el token se deriva de
forma determinista a partir de un secreto de la instalación y del id del
registro de token (`CardTokenCodec`, implementado en infraestructura con HMAC).
Sin el secreto, la huella no permite reconstruir el token; con la huella basta
para resolver una tarjeta escaneada.
"""

from __future__ import annotations

import hashlib
from typing import Protocol

TOKEN_PREFIX_LENGTH = 6

#: Versión de los tokens anteriores a LOY-29: eran aleatorios y se guardaban en
#: claro. Se conservan como huella (siguen resolviendo) pero no se pueden
#: reimprimir: hay que rotar el QR.
LEGACY_RANDOM_TOKEN_VERSION = 0
DERIVED_TOKEN_VERSION = 1


class CardTokenCodec(Protocol):
    def derive(self, token_id: str, version: int) -> str: ...


def hash_public_token(raw_token: str) -> str:
    return hashlib.sha256(str(raw_token).encode("utf-8")).hexdigest()


__all__ = [
    "CardTokenCodec", "DERIVED_TOKEN_VERSION", "LEGACY_RANDOM_TOKEN_VERSION",
    "TOKEN_PREFIX_LENGTH", "hash_public_token",
]
