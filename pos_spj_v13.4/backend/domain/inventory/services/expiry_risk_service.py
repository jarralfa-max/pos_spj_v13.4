"""ExpiryRiskService — classify a lot's expiration risk (§20, §43).

Pure domain logic. Drives INVENTORY_LOT_EXPIRING / INVENTORY_LOT_EXPIRED alerts:
EXPIRED (past), CRITICAL (<= critical_days), WARNING (<= warning_days), OK.
Thresholds come from configuration (§56), never hardcoded in UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from backend.domain.inventory.enums import ExpiryRisk


def _as_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


@dataclass(frozen=True, slots=True)
class ExpiryAssessment:
    risk: ExpiryRisk
    days_to_expiry: int | None


class ExpiryRiskService:
    def classify(self, expiration_date, *, as_of: date | None = None,
                 warning_days: int = 7, critical_days: int = 2) -> ExpiryAssessment:
        exp = _as_date(expiration_date)
        if exp is None:
            return ExpiryAssessment(ExpiryRisk.OK, None)
        ref = as_of or date.today()
        days = (exp - ref).days
        if days < 0:
            return ExpiryAssessment(ExpiryRisk.EXPIRED, days)
        if days <= critical_days:
            return ExpiryAssessment(ExpiryRisk.CRITICAL, days)
        if days <= warning_days:
            return ExpiryAssessment(ExpiryRisk.WARNING, days)
        return ExpiryAssessment(ExpiryRisk.OK, days)
