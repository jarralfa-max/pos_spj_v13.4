"""Safety stock policy (§72, BI-13) — 4 configurable methods, never a single
universal formula.

`SERVICE_LEVEL` ports the legacy `SafetyStockCalculator`'s formula (BI-6:
`Z·σ·√(lead_time)`, the only method the legacy engine had) exactly. The
other 3 (`FIXED_DAYS`, `DEMAND_VARIABILITY`, `CUSTOM`) are new — §72
explicitly asks for a configurable set, not one hardcoded formula.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.forecasting.enums import SafetyStockMethod
from backend.domain.forecasting.exceptions import ForecastingDomainError

#: Same Z-table convention as `confidence_interval.py` / legacy
#: SafetyStockCalculator — service levels, not confidence levels, but the
#: same fixed-table-over-approximation philosophy.
SERVICE_LEVEL_Z: dict[Decimal, Decimal] = {
    Decimal("0.90"): Decimal("1.2816"),
    Decimal("0.95"): Decimal("1.6449"),
    Decimal("0.975"): Decimal("1.9600"),
    Decimal("0.99"): Decimal("2.3263"),
    Decimal("0.999"): Decimal("3.0902"),
}


class UnsupportedSafetyStockMethodError(ForecastingDomainError):
    pass


def std_dev(daily_demand: tuple[Decimal, ...]) -> Decimal:
    if len(daily_demand) < 2:
        raise ForecastingDomainError("std_dev requires at least 2 observations")
    mean = sum(daily_demand, Decimal("0")) / Decimal(len(daily_demand))
    variance = sum(((v - mean) * (v - mean) for v in daily_demand), Decimal("0")) / Decimal(
        len(daily_demand) - 1)
    return variance.sqrt()


def safety_stock(
    method: SafetyStockMethod,
    *,
    avg_daily_demand: Decimal,
    lead_time_days: int,
    daily_demand_history: tuple[Decimal, ...] = (),
    service_level: Decimal = Decimal("0.95"),
    fixed_days: Decimal | None = None,
    lead_time_std_dev_days: Decimal = Decimal("0"),
    custom_value: Decimal | None = None,
) -> Decimal:
    if lead_time_days < 0:
        raise ValueError("lead_time_days must be >= 0")
    if avg_daily_demand < 0:
        raise ValueError("avg_daily_demand must be >= 0")

    if method == SafetyStockMethod.FIXED_DAYS:
        if fixed_days is None or fixed_days < 0:
            raise ValueError("FIXED_DAYS requires a non-negative fixed_days")
        return avg_daily_demand * fixed_days

    if method == SafetyStockMethod.SERVICE_LEVEL:
        if service_level not in SERVICE_LEVEL_Z:
            raise ValueError(f"service_level must be one of {sorted(SERVICE_LEVEL_Z)}")
        demand_std = std_dev(daily_demand_history)
        z = SERVICE_LEVEL_Z[service_level]
        return z * demand_std * Decimal(lead_time_days).sqrt()

    if method == SafetyStockMethod.DEMAND_VARIABILITY:
        if service_level not in SERVICE_LEVEL_Z:
            raise ValueError(f"service_level must be one of {sorted(SERVICE_LEVEL_Z)}")
        demand_std = std_dev(daily_demand_history)
        z = SERVICE_LEVEL_Z[service_level]
        # Combined demand + lead-time variability (both contribute to the risk
        # of stocking out during the lead time), not just demand variance
        # assuming a fixed lead time — this is what distinguishes this method
        # from SERVICE_LEVEL, which the legacy engine never modeled.
        term = (Decimal(lead_time_days) * demand_std * demand_std
                + avg_daily_demand * avg_daily_demand * lead_time_std_dev_days * lead_time_std_dev_days)
        return z * term.sqrt()

    if method == SafetyStockMethod.CUSTOM:
        if custom_value is None or custom_value < 0:
            raise ValueError("CUSTOM requires a non-negative custom_value")
        return custom_value

    raise UnsupportedSafetyStockMethodError(f"Unknown SafetyStockMethod: {method}")


def reorder_point(avg_daily_demand: Decimal, lead_time_days: int, safety_stock_qty: Decimal) -> Decimal:
    if avg_daily_demand < 0 or lead_time_days < 0 or safety_stock_qty < 0:
        raise ValueError("reorder_point inputs must be >= 0")
    return avg_daily_demand * Decimal(lead_time_days) + safety_stock_qty


def recommended_quantity(
    current_stock: Decimal,
    reorder_point_qty: Decimal,
    target_coverage_days: Decimal,
    avg_daily_demand: Decimal,
) -> Decimal:
    """How much to order so stock reaches `target_coverage_days` worth of
    demand above the reorder point — never negative (no "un-order")."""
    target_stock = reorder_point_qty + target_coverage_days * avg_daily_demand
    quantity = target_stock - current_stock
    return quantity if quantity > 0 else Decimal("0")


def days_coverage(current_stock: Decimal, avg_daily_demand: Decimal) -> Decimal | None:
    """None means infinite coverage (no demand to deplete stock)."""
    if avg_daily_demand == 0:
        return None
    if current_stock <= 0:
        return Decimal("0")
    return current_stock / avg_daily_demand


def urgency_level(days_cov: Decimal | None) -> str:
    if days_cov is None:
        return "NONE"
    if days_cov <= Decimal("0"):
        return "CRITICAL"
    if days_cov <= Decimal("3"):
        return "HIGH"
    if days_cov <= Decimal("7"):
        return "MEDIUM"
    return "LOW"
