"""ExternalProductRecord — a normalized record fetched from an external catalog (§15).

Stores the source (provenance), the external id, the normalized master-data fields,
the raw payload, a data-quality score and a status. It is NOT a product until it is
reviewed and imported; matching links it to an existing product when found.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.products.exceptions import (
    ExternalRecordNotReviewedError,
    InvalidExternalRecordError,
)
from backend.domain.products.external_enums import ExternalRecordStatus
from backend.domain.products.value_objects.data_quality_score import DataQualityScore
from backend.shared.ids import new_uuid


@dataclass
class ExternalProductRecord:
    source_id: str
    external_id: str
    name: str
    id: str = field(default_factory=new_uuid)
    barcode: str | None = None
    brand: str | None = None
    category: str | None = None
    net_weight: str | None = None
    unit: str | None = None
    raw_payload: str | None = None
    status: ExternalRecordStatus = ExternalRecordStatus.PENDING_REVIEW
    matched_product_id: str | None = None
    data_quality_score: DataQualityScore | None = None

    def __post_init__(self) -> None:
        if not self.source_id:
            raise InvalidExternalRecordError("El registro externo requiere fuente")
        if not self.external_id:
            raise InvalidExternalRecordError("El registro externo requiere id externo")
        if not (self.name or "").strip():
            raise InvalidExternalRecordError("El registro externo requiere nombre")
        if not isinstance(self.status, ExternalRecordStatus):
            self.status = ExternalRecordStatus(str(self.status))
        if self.data_quality_score is None:
            self.data_quality_score = DataQualityScore.from_fields(self._fields())

    def _fields(self) -> dict:
        return {"name": self.name, "barcode": self.barcode or "", "brand": self.brand or "",
                "category": self.category or "", "net_weight": self.net_weight or "",
                "unit": self.unit or ""}

    def mark_matched(self, product_id: str) -> None:
        if not product_id:
            raise InvalidExternalRecordError("El match requiere product_id")
        self.matched_product_id = product_id
        self.status = ExternalRecordStatus.MATCHED

    def approve(self) -> None:
        self.status = ExternalRecordStatus.APPROVED

    def reject(self) -> None:
        self.status = ExternalRecordStatus.REJECTED

    def mark_imported(self) -> None:
        if self.status not in (ExternalRecordStatus.APPROVED, ExternalRecordStatus.MATCHED):
            raise ExternalRecordNotReviewedError(
                "El registro externo debe revisarse/aprobarse antes de importar (§15)")
        self.status = ExternalRecordStatus.IMPORTED
