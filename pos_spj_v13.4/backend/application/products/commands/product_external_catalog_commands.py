"""Commands del catálogo externo (PROD-15: buscar, revisar, importar)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchExternalCatalogCommand:
    operation_id: str
    source_id: str
    query: str
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "source_id", "query")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class ApproveExternalRecordCommand:
    operation_id: str
    record_id: str
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "record_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class RejectExternalRecordCommand:
    operation_id: str
    record_id: str
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "record_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class ImportExternalRecordCommand:
    operation_id: str
    record_id: str
    user_id: str | None = None
    # Sólo se usan si el registro no tiene match a un producto existente — un
    # catálogo externo no conoce la clasificación interna del ERP.
    product_type: str = "RESALE_PRODUCT"
    base_unit_id: str | None = None
    category_id: str | None = None
    auto_generate_code: bool = True

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "record_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")
