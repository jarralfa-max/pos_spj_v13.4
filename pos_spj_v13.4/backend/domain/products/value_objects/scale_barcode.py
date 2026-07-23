"""ScaleBarcode — parsing a scale-printed barcode with embedded weight/price (§12, §17).

A weighing scale prints an EAN-13 whose digits embed a PLU/item code and either the
real weight or the computed price. The exact layout is store-configurable, so the
format is data (``ScaleBarcodeFormat``), never hardcoded. Parsing returns the PLU
and a Decimal value (weight in the configured unit, or money) — never a float.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.products.exceptions import InvalidScaleBarcodeError


@dataclass(frozen=True)
class ScaleBarcodeFormat:
    prefix: str                 # leading flag digits printed by the scale (e.g. "2")
    plu_start: int              # 0-based index where the item/PLU code starts
    plu_length: int
    value_start: int
    value_length: int
    value_kind: str = "WEIGHT"  # WEIGHT | PRICE
    value_decimals: int = 3     # implied decimals in the embedded integer

    def __post_init__(self) -> None:
        if not self.prefix or not self.prefix.isdigit():
            raise InvalidScaleBarcodeError("El prefijo de báscula debe ser numérico")
        if self.plu_length <= 0 or self.value_length <= 0:
            raise InvalidScaleBarcodeError("Longitudes de PLU/valor inválidas")
        if self.value_kind not in ("WEIGHT", "PRICE"):
            raise InvalidScaleBarcodeError("value_kind debe ser WEIGHT o PRICE")


@dataclass(frozen=True)
class ScaleBarcodeReading:
    plu: str
    value: Decimal
    value_kind: str


def parse_scale_barcode(value: str, fmt: ScaleBarcodeFormat) -> ScaleBarcodeReading:
    raw = (value or "").strip()
    if not raw.isdigit():
        raise InvalidScaleBarcodeError(f"Código de báscula no numérico: {value!r}")
    if not raw.startswith(fmt.prefix):
        raise InvalidScaleBarcodeError(
            f"El código no comienza con el prefijo de báscula {fmt.prefix!r}")
    plu_end = fmt.plu_start + fmt.plu_length
    value_end = fmt.value_start + fmt.value_length
    if len(raw) < max(plu_end, value_end):
        raise InvalidScaleBarcodeError("El código de báscula es demasiado corto")
    plu = raw[fmt.plu_start:plu_end]
    embedded = raw[fmt.value_start:value_end]
    scaled = Decimal(embedded).scaleb(-int(fmt.value_decimals))
    return ScaleBarcodeReading(plu=plu, value=scaled, value_kind=fmt.value_kind)
