"""Chart DTOs (FASE DS-5) — the transport between QueryServices and the chart view.

A ChartDataDTO carries data + meaning only. It must NOT contain colors, CSS,
HTML, JavaScript, queries or callbacks — colors are assigned from the theme
palette by the chart bridge, presentation by the renderer.
"""

from backend.application.dto.charts.chart_data import (
    ChartAnnotationDTO,
    ChartDataDTO,
    ChartSeriesDTO,
    ChartState,
    ChartType,
    DataFreshnessDTO,
    FreshnessState,
)

__all__ = [
    "ChartAnnotationDTO",
    "ChartDataDTO",
    "ChartSeriesDTO",
    "ChartState",
    "ChartType",
    "DataFreshnessDTO",
    "FreshnessState",
]
