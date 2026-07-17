"""ChartDataDTO and friends (FASE DS-5).

Pure data. No colors, CSS, HTML, JS, queries or callbacks — those belong to the
theme/renderer. Immutable dataclasses so a DTO can't be mutated after a
QueryService produces it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, Sequence


class ChartType:
    LINE = "line"
    AREA = "area"
    BAR = "bar"
    HORIZONTAL_BAR = "horizontal_bar"
    STACKED_BAR = "stacked_bar"
    STACKED_AREA = "stacked_area"
    DONUT = "donut"
    PIE = "pie"
    GAUGE = "gauge"
    HEATMAP = "heatmap"
    WATERFALL = "waterfall"
    SCATTER = "scatter"
    COMBO = "combo"
    FUNNEL = "funnel"
    TIMELINE = "timeline"


CANONICAL_CHART_TYPES = frozenset({
    ChartType.LINE, ChartType.AREA, ChartType.BAR, ChartType.HORIZONTAL_BAR,
    ChartType.STACKED_BAR, ChartType.STACKED_AREA, ChartType.DONUT, ChartType.PIE,
    ChartType.GAUGE, ChartType.HEATMAP, ChartType.WATERFALL, ChartType.SCATTER,
    ChartType.COMBO, ChartType.FUNNEL, ChartType.TIMELINE,
})


class ChartState:
    READY = "READY"
    LOADING = "LOADING"
    EMPTY = "EMPTY"
    ERROR = "ERROR"
    STALE = "STALE"
    OFFLINE = "OFFLINE"
    PARTIAL_DATA = "PARTIAL_DATA"


class FreshnessState:
    LIVE = "LIVE"
    FRESH = "FRESH"
    DELAYED = "DELAYED"
    STALE = "STALE"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"
    OFFLINE = "OFFLINE"


@dataclass(frozen=True)
class ChartSeriesDTO:
    name: str
    data: tuple[float | None, ...]
    #: optional per-series type override for combo charts (e.g. "line" over bars)
    series_type: str | None = None
    #: optional stack group id (stacked_bar / stacked_area)
    stack: str | None = None
    #: optional semantic role that maps to a status color (success/warning/danger/...)
    semantic: str | None = None


@dataclass(frozen=True)
class ChartAnnotationDTO:
    kind: str          # "target" | "average" | "threshold"
    value: float
    label: str = ""


@dataclass(frozen=True)
class DataFreshnessDTO:
    generated_at: datetime
    last_source_event_at: datetime | None = None
    state: str = FreshnessState.UNKNOWN
    missing_sources: tuple[str, ...] = ()
    delay_seconds: int | None = None


@dataclass(frozen=True)
class ChartDataDTO:
    chart_id: str
    chart_type: str
    title: str
    subtitle: str | None
    categories: tuple[str, ...]
    series: tuple[ChartSeriesDTO, ...]
    unit: str | None = None
    currency_code: str | None = None
    generated_at: datetime | None = None
    freshness_state: str = FreshnessState.UNKNOWN
    annotations: tuple[ChartAnnotationDTO, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)
    state: str = ChartState.READY
    empty_message: str | None = None
    accessibility_summary: str | None = None

    def __post_init__(self) -> None:
        if self.chart_type not in CANONICAL_CHART_TYPES:
            raise ValueError(
                f"chart_type inválido: {self.chart_type!r} "
                f"(usa ChartType.*: {sorted(CANONICAL_CHART_TYPES)})")

    @staticmethod
    def empty(chart_id: str, chart_type: str, title: str,
              message: str = "Sin datos para mostrar") -> "ChartDataDTO":
        return ChartDataDTO(
            chart_id=chart_id, chart_type=chart_type, title=title, subtitle=None,
            categories=(), series=(), state=ChartState.EMPTY, empty_message=message)

    def is_empty(self) -> bool:
        return self.state == ChartState.EMPTY or not self.series or not any(
            any(v is not None for v in s.data) for s in self.series)


def series_from(name: str, values: Sequence[float | None], **kwargs) -> ChartSeriesDTO:
    """Convenience builder that freezes ``values`` into a tuple."""
    return ChartSeriesDTO(name=name, data=tuple(values), **kwargs)
