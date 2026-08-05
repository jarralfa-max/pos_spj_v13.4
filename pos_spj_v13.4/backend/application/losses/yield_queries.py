"""Read models for yield monitoring and open alerts."""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class YieldVarianceView:
    id: str
    production_id: str
    product_id: str
    expected_output: Decimal
    actual_output: Decimal
    variance_quantity: Decimal
    variance_pct: Decimal
    severity: str
    detected_at: str


@dataclass(frozen=True)
class YieldAlertView:
    id: str
    variance_id: str
    severity: str
    expected_yield_pct: Decimal
    actual_yield_pct: Decimal
    lower_tolerance_pct: Decimal
    upper_tolerance_pct: Decimal
    message: str
    created_at: str


class YieldMonitoringQueryService:
    def __init__(self, repository): self._repository = repository

    def recent_variances(self, *, branch_id: str, limit: int = 100):
        return tuple(YieldVarianceView(
            str(r[0]), str(r[1]), str(r[2]), Decimal(str(r[3])), Decimal(str(r[4])),
            Decimal(str(r[5])), Decimal(str(r[6])), str(r[7]), str(r[8]))
            for r in self._repository.recent_variances(branch_id=branch_id, limit=limit))

    def open_alerts(self, *, branch_id: str, limit: int = 100):
        return tuple(YieldAlertView(
            str(r[0]), str(r[1]), str(r[2]), Decimal(str(r[3])), Decimal(str(r[4])),
            Decimal(str(r[5])), Decimal(str(r[6])), str(r[7]), str(r[8]))
            for r in self._repository.open_alerts(branch_id=branch_id, limit=limit))
