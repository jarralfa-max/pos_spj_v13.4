"""Canonical chart data DTOs for frontend chart rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class ChartSeriesDTO:
    """Business series supplied by QueryServices, with no visual styling."""

    key: str
    name: str
    values: tuple[Decimal | int | None, ...]
    series_type: str
    stack_group: str | None = None
    axis: str = "left"
    formatter: str | None = None


@dataclass(frozen=True)
class ChartAnnotationDTO:
    """Business annotation such as goals, limits, events or tolerances."""

    key: str
    label: str
    category: str | None
    value: Decimal | int | None
    annotation_type: str


@dataclass(frozen=True)
class ChartDataDTO:
    """Transport-only chart data with no presentation payload or colors."""

    chart_id: str
    chart_type: str
    title: str
    subtitle: str | None
    categories: tuple[str, ...]
    series: tuple[ChartSeriesDTO, ...]
    unit: str | None
    currency_code: str | None
    generated_at: datetime
    freshness_state: str
    annotations: tuple[ChartAnnotationDTO, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    state: str = "READY"
    empty_message: str | None = None
    accessibility_summary: str | None = None
