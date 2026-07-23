"""Barcode / alternate-code enums for the products bounded context (§17).

PROD-7. Products supports many code standards (internal SKU, EAN/UPC/GTIN retail
codes, PLU, QR, supplier codes, scale barcodes with embedded weight, and future
lot / carcass tags). The architecture is prepared for label payloads (canal, lote,
corte, fecha de sacrificio, caducidad, peso real, temperatura, trazabilidad).
"""

from __future__ import annotations

from enum import Enum


class BarcodeType(str, Enum):
    INTERNAL_SKU = "INTERNAL_SKU"
    EAN = "EAN"
    UPC = "UPC"
    GTIN = "GTIN"
    PLU = "PLU"
    QR = "QR"
    SUPPLIER_CODE = "SUPPLIER_CODE"
    SCALE_BARCODE = "SCALE_BARCODE"
    LOT_LABEL = "LOT_LABEL"
    CARCASS_TAG = "CARCASS_TAG"
    CUSTOM = "CUSTOM"


# Tipos con dígito verificador GS1 (EAN-13/UPC-A/GTIN) — se valida checksum.
CHECKSUM_TYPES = frozenset({BarcodeType.EAN, BarcodeType.UPC, BarcodeType.GTIN})

# Tipos numéricos puros.
NUMERIC_TYPES = frozenset({
    BarcodeType.EAN, BarcodeType.UPC, BarcodeType.GTIN,
    BarcodeType.PLU, BarcodeType.SCALE_BARCODE,
})
