"""Price-change impact math (§32-35, BI-16; extracted BI-19).

Pulled out of `pricing_decision.py` so `PricingWhatIfService` (BI-19,
scenario_planning) can reuse the exact same first-order log-linear impact
formula for an arbitrary *simulated* price, not just the one
`decide_price_recommendation()` auto-picks — one formula, two callers,
never two implementations that could drift apart.
"""

from __future__ import annotations

from decimal import Decimal


def compute_price_change_impact(
    *,
    current_price: Decimal,
    current_cost: Decimal | None,
    elasticity: Decimal,
    suggested_price: Decimal,
    current_margin_pct: Decimal | None = None,
) -> tuple[Decimal, Decimal | None, Decimal]:
    """Returns (expected_volume_change_pct, expected_margin_change_pct,
    expected_revenue_change_pct). `%ΔQ ≈ E·%ΔP` (log-linear first order);
    `%ΔIngreso ≈ %ΔP + %ΔQ`. `expected_margin_change_pct` is `None` without
    a cost (a margin can't be computed without one)."""
    if current_price <= 0:
        raise ValueError("current_price must be > 0")
    price_change_pct = (suggested_price - current_price) / current_price * Decimal("100")
    volume_change_pct = elasticity * price_change_pct
    revenue_change_pct = price_change_pct + volume_change_pct

    margin_change_pct = None
    if current_cost is not None and suggested_price > 0:
        new_margin_pct = (suggested_price - current_cost) / suggested_price * Decimal("100")
        baseline_margin_pct = (
            current_margin_pct if current_margin_pct is not None
            else (current_price - current_cost) / current_price * Decimal("100")
        )
        margin_change_pct = new_margin_pct - baseline_margin_pct

    return volume_change_pct, margin_change_pct, revenue_change_pct
