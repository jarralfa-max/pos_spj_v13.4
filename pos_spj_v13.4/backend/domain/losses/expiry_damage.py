"""Pure risk policy for lots affected by expiry or physical damage."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import Enum

from backend.domain.losses.exceptions import LossInvariantError


class DamageSeverity(str, Enum):
    NONE = "NONE"
    MINOR = "MINOR"
    MAJOR = "MAJOR"
    UNSAFE = "UNSAFE"


class LotRiskLevel(str, Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True, slots=True)
class LotRiskAssessment:
    risk_level: LotRiskLevel
    expiry_risk: str
    damage_severity: DamageSeverity
    days_to_expiry: int | None
    quantity: Decimal
    weight: Decimal


def _decimal(value, field: str) -> Decimal:
    if isinstance(value, (bool, float)):
        raise LossInvariantError(f"{field} no admite float")
    try:
        result = Decimal(str(value or "0"))
    except (InvalidOperation, ValueError):
        raise LossInvariantError(f"{field} no es decimal válido") from None
    if not result.is_finite() or result < 0:
        raise LossInvariantError(f"{field} debe ser finito y no negativo")
    return result


class ExpiryDamageRiskPolicy:
    """Combines configured shelf-life thresholds with an explicit damage grade."""

    def assess(self, *, expiration_date=None, as_of: date | None = None,
               warning_days: int = 7, critical_days: int = 2,
               damage_severity: DamageSeverity = DamageSeverity.NONE,
               quantity=0, weight=0) -> LotRiskAssessment:
        if warning_days < 0 or critical_days < 0 or critical_days > warning_days:
            raise LossInvariantError("Los umbrales de caducidad son inválidos")
        qty, wgt = _decimal(quantity, "quantity"), _decimal(weight, "weight")
        if qty <= 0 and wgt <= 0:
            raise LossInvariantError("La evaluación requiere cantidad o peso")
        severity = DamageSeverity(damage_severity)
        days = None
        expiry_risk = "NOT_APPLICABLE"
        expiry_level = LotRiskLevel.NORMAL
        if expiration_date:
            expiry = (expiration_date if isinstance(expiration_date, date)
                      else date.fromisoformat(str(expiration_date)[:10]))
            days = (expiry - (as_of or date.today())).days
            if days < 0:
                expiry_risk, expiry_level = "EXPIRED", LotRiskLevel.CRITICAL
            elif days <= critical_days:
                expiry_risk, expiry_level = "CRITICAL", LotRiskLevel.CRITICAL
            elif days <= warning_days:
                expiry_risk, expiry_level = "WARNING", LotRiskLevel.WARNING
            else:
                expiry_risk = "OK"
        damage_level = {
            DamageSeverity.NONE: LotRiskLevel.NORMAL,
            DamageSeverity.MINOR: LotRiskLevel.WARNING,
            DamageSeverity.MAJOR: LotRiskLevel.HIGH,
            DamageSeverity.UNSAFE: LotRiskLevel.CRITICAL,
        }[severity]
        order = list(LotRiskLevel)
        combined = max((expiry_level, damage_level), key=order.index)
        return LotRiskAssessment(combined, expiry_risk, severity, days, qty, wgt)
