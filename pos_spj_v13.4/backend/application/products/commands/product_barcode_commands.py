"""Commands de códigos de barras y códigos alternos (PROD-7)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssignBarcodeCommand:
    operation_id: str
    product_id: str
    value: str
    barcode_type: str
    user_id: str | None = None
    variant_id: str | None = None
    is_primary: bool = False

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "product_id", "value", "barcode_type")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class SetBarcodeActiveCommand:
    operation_id: str
    barcode_id: str
    active: bool
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "barcode_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class AddAlternateCodeCommand:
    operation_id: str
    product_id: str
    code: str
    user_id: str | None = None
    code_type: str = "SUPPLIER_CODE"
    supplier_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "product_id", "code")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")
