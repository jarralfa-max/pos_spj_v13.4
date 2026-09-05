"""Confidence interval construction (§25, BI-11).

A bare point forecast is never sufficient (§25: "No mostrar una predicción
como certeza") — every `ForecastResultPoint` needs a lower/upper bound. This
derives that bound from a backtest's RMSE (the error the model actually
made on held-out data — BI-10 — never a guess) and a z-score for the
requested confidence level, the same Z-table convention
`SafetyStockCalculator` (legacy, catalogued in BI-6) already used for
service levels.
"""

from __future__ import annotations

from decimal import Decimal

#: Supported confidence levels — deliberately a fixed table rather than an
#: interpolated/approximated z-score for arbitrary levels, so a caller never
#: gets a silently-wrong interval for an unsupported level.
Z_SCORES: dict[Decimal, Decimal] = {
    Decimal("0.80"): Decimal("1.2816"),
    Decimal("0.90"): Decimal("1.6449"),
    Decimal("0.95"): Decimal("1.9600"),
    Decimal("0.99"): Decimal("2.5758"),
}


def build_bounds(
    point_forecasts: tuple[Decimal, ...],
    rmse: Decimal,
    confidence_level: Decimal,
    clamp_min: Decimal | None = None,
) -> tuple[tuple[Decimal, Decimal], ...]:
    """Returns a (lower_bound, upper_bound) pair per point forecast, same
    order. `clamp_min` floors the lower bound (e.g. `Decimal("0")` for a
    quantity series that can never be forecast negative) — left `None` for
    metrics where negative values are meaningful (e.g. margin)."""
    if confidence_level not in Z_SCORES:
        raise ValueError(
            f"confidence_level {confidence_level} not supported; use one of "
            f"{sorted(Z_SCORES)}"
        )
    if rmse < 0:
        raise ValueError("rmse must be >= 0")
    margin = rmse * Z_SCORES[confidence_level]
    bounds = []
    for point in point_forecasts:
        lower = point - margin
        upper = point + margin
        if clamp_min is not None and lower < clamp_min:
            lower = clamp_min
        bounds.append((lower, upper))
    return tuple(bounds)
