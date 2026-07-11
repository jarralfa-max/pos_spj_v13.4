"""DTOs / read models for the Business Intelligence dashboard.

Backend code is written in English; user-facing strings (titles, tooltips) stay
in Spanish because they are rendered verbatim by the UI. These DTOs are the
stable contract the PyQt UI and any future API consume — no SQL, no cursors, no
domain identity as integers (REGLA CERO: UUIDv7 strings only).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any


# ── Filters ───────────────────────────────────────────────────────────────────

_PRESETS = ("today", "yesterday", "week", "month", "last_month", "custom")


@dataclass(frozen=True)
class DashboardFilters:
    """Global, combinable dashboard filters. Persisted per UI session.

    branch_id/customer_id/supplier_id are UUIDv7 strings (never int-cast).
    channel/category/payment_method/product_type are literal string codes.
    """

    preset: str = "month"
    date_from: str = ""      # resolved ISO date 'YYYY-MM-DD'
    date_to: str = ""
    branch_id: str = ""
    channel: str = ""        # tienda_fisica | delivery_propio | delivery_terceros | mayoreo | ""(todos)
    category: str = ""
    payment_method: str = ""
    customer_id: str = ""
    supplier_id: str = ""
    product_type: str = ""

    def resolved(self, today: date | None = None) -> "DashboardFilters":
        """Return a copy with date_from/date_to filled from the preset."""
        if self.preset == "custom" and self.date_from and self.date_to:
            return self
        fi, ff = resolve_range(self.preset, today)
        return DashboardFilters(
            preset=self.preset, date_from=fi, date_to=ff,
            branch_id=self.branch_id, channel=self.channel,
            category=self.category, payment_method=self.payment_method,
            customer_id=self.customer_id, supplier_id=self.supplier_id,
            product_type=self.product_type,
        )

    def previous_period(self) -> tuple[str, str]:
        """Equivalent immediately-preceding window, for comparison KPIs."""
        f = self.resolved()
        d0 = date.fromisoformat(f.date_from)
        d1 = date.fromisoformat(f.date_to)
        span = (d1 - d0).days + 1
        prev_end = d0 - timedelta(days=1)
        prev_start = prev_end - timedelta(days=span - 1)
        return prev_start.isoformat(), prev_end.isoformat()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_range(preset: str, today: date | None = None) -> tuple[str, str]:
    """Resolve a preset to (date_from, date_to) ISO strings."""
    hoy = today or date.today()
    if preset == "today":
        return hoy.isoformat(), hoy.isoformat()
    if preset == "yesterday":
        y = hoy - timedelta(days=1)
        return y.isoformat(), y.isoformat()
    if preset == "week":
        start = hoy - timedelta(days=hoy.weekday())
        return start.isoformat(), hoy.isoformat()
    if preset == "last_month":
        first_this = hoy.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        return last_prev.replace(day=1).isoformat(), last_prev.isoformat()
    # default: this month
    return hoy.replace(day=1).isoformat(), hoy.isoformat()


# ── KPI cards ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class KpiCard:
    key: str
    title: str                      # Spanish, user-facing
    value: float
    unit: str = ""                  # "$", "%", "", "x"
    previous_value: float = 0.0
    delta_pct: float | None = None  # % change vs previous
    delta_points: float | None = None  # absolute point change (for % KPIs)
    direction: str = "flat"         # up | down | flat
    semantic: str = "neutral"       # positive | negative | neutral
    tooltip: str = ""               # Spanish
    drilldown: str = ""             # target tab key
    formula: str = ""               # documented formula

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_kpi(key, title, value, previous, *, unit="$", higher_is_better=True,
             is_percent=False, tooltip="", drilldown="", formula="") -> KpiCard:
    """Build a KpiCard computing delta + direction + semantic color."""
    value = float(value or 0)
    previous = float(previous or 0)
    delta_pct = None
    delta_points = None
    if is_percent:
        delta_points = round(value - previous, 2)
        change = delta_points
    else:
        if previous:
            delta_pct = round((value - previous) / abs(previous) * 100, 1)
        change = (value - previous)
    if change > 0:
        direction = "up"
    elif change < 0:
        direction = "down"
    else:
        direction = "flat"
    if direction == "flat":
        semantic = "neutral"
    else:
        good = (direction == "up") == higher_is_better
        semantic = "positive" if good else "negative"
    return KpiCard(
        key=key, title=title, value=round(value, 2), unit=unit,
        previous_value=round(previous, 2), delta_pct=delta_pct,
        delta_points=delta_points, direction=direction, semantic=semantic,
        tooltip=tooltip, drilldown=drilldown, formula=formula,
    )


# ── Charts / highlights / alerts / insights ───────────────────────────────────

@dataclass(frozen=True)
class ChartData:
    key: str
    kind: str                       # line | bar | hbar | donut | combo
    title: str
    labels: list[str] = field(default_factory=list)
    series: list[dict[str, Any]] = field(default_factory=list)  # [{name,color,values}]
    unit: str = "$"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HighlightCard:
    key: str
    title: str
    name: str
    value: float
    share_pct: float = 0.0
    unit: str = "$"
    drilldown: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Alert:
    level: str                      # info | warning | critical
    code: str
    title: str
    detail: str
    metric: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Insight:
    code: str
    title: str
    detail: str
    drilldown: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Prediction:
    key: str
    title: str
    value: float
    unit: str = "$"
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DashboardPayload:
    filters: dict[str, Any]
    kpis: list[dict[str, Any]]
    charts: dict[str, dict[str, Any]]
    highlights: dict[str, dict[str, Any]]
    alerts: list[dict[str, Any]]
    predictions: dict[str, dict[str, Any]]
    insights: list[dict[str, Any]]
    allowed_sections: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
