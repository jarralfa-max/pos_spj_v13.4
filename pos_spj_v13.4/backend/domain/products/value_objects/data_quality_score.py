"""DataQualityScore — a 0-100 completeness/quality score (§15, §35).

Computed from how many required master-data fields an external record carries.
Feeds the "data quality" page and the acceptance policy. Decimal-free integer 0-100.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.products.exceptions import InvalidExternalRecordError

_WEIGHTED_FIELDS = ("name", "barcode", "brand", "category", "net_weight", "unit")


@dataclass(frozen=True)
class DataQualityScore:
    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise InvalidExternalRecordError("El score de calidad debe ser entero")
        if not (0 <= self.value <= 100):
            raise InvalidExternalRecordError("El score de calidad debe estar en [0, 100]")

    @classmethod
    def from_fields(cls, fields: dict) -> "DataQualityScore":
        present = sum(1 for f in _WEIGHTED_FIELDS if (fields.get(f) or "").strip())
        return cls(round(present * 100 / len(_WEIGHTED_FIELDS)))

    def is_acceptable(self, minimum: int = 50) -> bool:
        return self.value >= minimum
