"""External data acceptance policy (§15) — external data must be reviewed.

"external_record_requires_review": a record fetched from an external catalog may
not become a canonical product until it is reviewed/approved (§15, §39 segregation:
whoever imports does not auto-approve). A minimum data-quality score may also be
required.
"""

from __future__ import annotations

from backend.domain.products.entities.external_product_record import (
    ExternalProductRecord,
)
from backend.domain.products.exceptions import ExternalRecordNotReviewedError
from backend.domain.products.external_enums import ExternalRecordStatus


def ensure_importable(
    record: ExternalProductRecord,
    *,
    require_review: bool = True,
    minimum_quality: int = 0,
) -> None:
    if require_review and record.status not in (
            ExternalRecordStatus.APPROVED, ExternalRecordStatus.MATCHED):
        raise ExternalRecordNotReviewedError(
            "El registro externo requiere revisión antes de importar (§15)")
    score = record.data_quality_score
    if score is not None and not score.is_acceptable(minimum_quality):
        raise ExternalRecordNotReviewedError(
            f"La calidad de datos ({score.value}) es menor al mínimo ({minimum_quality})")
