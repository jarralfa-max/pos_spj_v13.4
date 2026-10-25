"""Código público de UNA pieza de un lote de cupones o vales.

Forma impresa (Code 128 y texto legible):  `VAL-7K2Q-M9XA-4RTD-PBN3`
Forma canónica (la que se busca):          `VAL7K2QM9XA4RTDPBN3`

- Prefijo `CUP` (cupón: descuento) o `VAL` (vale: forma de pago). El POS lo usa
  para llevar el código a donde corresponde sin que el cajero sepa la diferencia.
- 16 caracteres Base32 (A–Z, 2–7: sin 0/1/8/9 para no confundir 0 con O ni 1 con
  I al teclear) = 80 bits, derivados con HMAC del secreto de la instalación.
- Sólo se GUARDA su huella SHA-256; el código completo no vive en ninguna tabla.
- El folio (`VAL7F3A-00001`) identifica la pieza para personas e informes, pero
  NO sirve para canjear: no es secreto.
"""

from __future__ import annotations

import hashlib
import re

PIECE_PREFIXES = ("CUP", "VAL")
PIECE_TOKEN_LENGTH = 16
_BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
_SHAPE = re.compile(rf"^(CUP|VAL)([{_BASE32}]{{{PIECE_TOKEN_LENGTH}}})$")


def normalize_piece_code(text: str) -> str | None:
    """Forma canónica de un código de pieza, o `None` si no tiene esa forma.

    Tolera lo que hace un humano o un lector: minúsculas, guiones, espacios."""
    limpio = re.sub(r"[\s\-_]", "", str(text or "")).upper()
    return limpio if _SHAPE.match(limpio) else None


def piece_kind_prefix(canonical: str) -> str:
    return canonical[:3]


def hash_piece_code(canonical: str) -> str:
    """Huella de la forma CANÓNICA: la impresa y la tecleada dan la misma."""
    canonico = normalize_piece_code(canonical) or str(canonical)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def printable_piece_code(canonical: str) -> str:
    """`VAL7K2QM9XA4RTDPBN3` → `VAL-7K2Q-M9XA-4RTD-PBN3`."""
    cuerpo = canonical[3:]
    return "-".join([canonical[:3], *(cuerpo[i:i + 4] for i in range(0, len(cuerpo), 4))])


__all__ = ["PIECE_PREFIXES", "PIECE_TOKEN_LENGTH", "hash_piece_code", "normalize_piece_code",
           "piece_kind_prefix", "printable_piece_code"]
