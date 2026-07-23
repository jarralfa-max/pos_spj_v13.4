"""Barcode — a validated barcode value object (§17).

Normalizes the payload and, for GS1 numeric standards (EAN-13, UPC-A, GTIN),
verifies the modulo-10 check digit. Non-numeric standards (QR, supplier code,
carcass tag) are stored verbatim after trimming. The value object never carries
the assignment (product/variant) — that is ``ProductBarcode`` — so the same
validated value can be reused.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.products.barcode_enums import (
    CHECKSUM_TYPES,
    NUMERIC_TYPES,
    BarcodeType,
)
from backend.domain.products.exceptions import InvalidBarcodeError


def gs1_check_digit(digits: str) -> int:
    """GS1 modulo-10 check digit over all but the last position."""
    total = 0
    # weights alternate 3,1 from the rightmost payload digit
    for i, ch in enumerate(reversed(digits)):
        weight = 3 if i % 2 == 0 else 1
        total += int(ch) * weight
    return (10 - (total % 10)) % 10


def _valid_gs1(value: str, expected_len: int | None = None) -> bool:
    if not value.isdigit():
        return False
    if expected_len is not None and len(value) != expected_len:
        return False
    if len(value) < 8:
        return False
    body, check = value[:-1], int(value[-1])
    return gs1_check_digit(body) == check


@dataclass(frozen=True)
class Barcode:
    value: str
    barcode_type: BarcodeType

    def __post_init__(self) -> None:
        raw = (self.value or "").strip()
        if not raw:
            raise InvalidBarcodeError("El código de barras no puede estar vacío")
        if not isinstance(self.barcode_type, BarcodeType):
            try:
                object.__setattr__(self, "barcode_type", BarcodeType(str(self.barcode_type)))
            except ValueError as exc:
                raise InvalidBarcodeError(
                    f"Tipo de código inválido: {self.barcode_type!r}") from exc
        if self.barcode_type in NUMERIC_TYPES and not raw.isdigit():
            raise InvalidBarcodeError(
                f"El código {self.barcode_type.value} debe ser numérico: {raw!r}")
        if self.barcode_type in CHECKSUM_TYPES:
            expected = {BarcodeType.EAN: 13, BarcodeType.UPC: 12}.get(self.barcode_type)
            if not _valid_gs1(raw, expected):
                raise InvalidBarcodeError(
                    f"Dígito verificador inválido para {self.barcode_type.value}: {raw!r}")
        object.__setattr__(self, "value", raw)

    def __str__(self) -> str:
        return self.value
