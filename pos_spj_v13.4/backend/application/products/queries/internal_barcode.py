"""Códigos de barras internos (PROD-23).

Para el producto que necesita código de barras y no trae uno de fabricante: un
EAN-13 de circulación restringida (prefijo GS1 04, ver
``value_objects/barcode.py``) con consecutivo propio.

* ``preview_internal_barcode``: el siguiente libre, sin consumir (el diálogo lo
  muestra; un código ya usado — capturado a mano o importado — se salta).
* ``advance_internal_barcode_sequence``: al ASIGNAR cualquier EAN interno el
  consecutivo avanza más allá de él, dentro de la transacción de la asignación;
  así lo que se ofrece después nunca repite.
"""

from __future__ import annotations

from backend.domain.products.value_objects.barcode import (
    internal_ean13,
    internal_ean_sequence,
)
from backend.infrastructure.db.repositories.products.code_sequence_repository import (
    ProductCodeSequenceRepository,
)

SEQUENCE_KEY = "BARCODE-EAN13-04"


def _taken(connection, value: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM product_barcodes WHERE barcode_value=? LIMIT 1", (value,)
    ).fetchone() is not None


def preview_internal_barcode(connection) -> str:
    sequence = ProductCodeSequenceRepository(connection).peek(SEQUENCE_KEY)
    value = internal_ean13(sequence)
    while _taken(connection, value):
        sequence += 1
        value = internal_ean13(sequence)
    return value


def advance_internal_barcode_sequence(connection, value: str) -> None:
    sequence = internal_ean_sequence(value)
    if sequence is not None:
        ProductCodeSequenceRepository(connection).advance_to(
            SEQUENCE_KEY, sequence + 1, padding=10)
