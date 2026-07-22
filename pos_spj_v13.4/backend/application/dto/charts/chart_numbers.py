"""Chart number coercion (display boundary).

Charts render floating-point series (ECharts); domain values are Decimal. This
helper is the single, explicit Decimal→chart-number crossing, kept OUT of the
Decimal-only bounded contexts so those stay float-free while still feeding charts.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


def to_chart_number(value) -> float:
    """Coerce a Decimal/int/str quantity to a chart float. None/blank → 0.0."""
    if value is None or value == "":
        return 0.0
    if isinstance(value, float):
        return value
    try:
        return float(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return 0.0
