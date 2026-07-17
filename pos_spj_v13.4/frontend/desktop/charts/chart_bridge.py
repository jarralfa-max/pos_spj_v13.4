"""Chart bridge (FASE DS-5).

Turns a color-free ``ChartDataDTO`` + the current theme into:
  * a JSON-safe payload for the ECharts renderer (colors assigned here from the
    theme palette — never from the DTO), and
  * a tabular alternative (headers + rows) for accessibility.

No querying, no HTML, no widget code. Pure transformation.
"""

from __future__ import annotations

import json
from datetime import datetime

from backend.application.dto.charts.chart_data import ChartDataDTO, ChartState, ChartType
from frontend.desktop.themes.semantic_colors import ChartPalette, SemanticColors

#: chart-type families that draw from the categorical palette
_CATEGORICAL_TYPES = {
    ChartType.LINE, ChartType.AREA, ChartType.BAR, ChartType.HORIZONTAL_BAR,
    ChartType.STACKED_BAR, ChartType.STACKED_AREA, ChartType.DONUT, ChartType.PIE,
    ChartType.SCATTER, ChartType.COMBO, ChartType.FUNNEL, ChartType.TIMELINE,
}


def _series_color(index: int, semantic: str | None) -> str:
    if semantic and semantic in ChartPalette.STATUS:
        return ChartPalette.STATUS[semantic]
    palette = ChartPalette.CATEGORICAL
    return palette[index % len(palette)]


def build_chart_payload(dto: ChartDataDTO, theme: str = "light") -> dict:
    """Build the JSON-safe spec the JS renderer consumes. Colors come from theme."""
    colors = SemanticColors.for_theme(theme)
    series_payload = []
    for index, series in enumerate(dto.series):
        series_payload.append({
            "name": series.name,
            "data": [None if v is None else float(v) for v in series.data],
            "type": series.series_type,          # None → renderer uses chart_type
            "stack": series.stack,
            "color": _series_color(index, series.semantic),
        })
    annotations = [
        {"kind": a.kind, "value": float(a.value), "label": a.label}
        for a in dto.annotations
    ]
    return {
        "chartId": dto.chart_id,
        "chartType": dto.chart_type,
        "title": dto.title,
        "subtitle": dto.subtitle,
        "categories": list(dto.categories),
        "series": series_payload,
        "unit": dto.unit,
        "currencyCode": dto.currency_code,
        "state": dto.state,
        "emptyMessage": dto.empty_message,
        "annotations": annotations,
        "accessibilitySummary": dto.accessibility_summary,
        "theme": {
            "name": theme,
            "text": colors.TEXT_PRIMARY,
            "mutedText": colors.TEXT_MUTED,
            "axis": colors.BORDER_STRONG,
            "grid": colors.BORDER_SUBTLE,
            "surface": colors.SURFACE,
            "tooltipBg": colors.TOOLTIP_BACKGROUND,
            "tooltipText": colors.TOOLTIP_TEXT,
        },
        "palette": list(ChartPalette.CATEGORICAL),
    }


def to_json(dto: ChartDataDTO, theme: str = "light") -> str:
    """JSON for safe embedding (``</`` escaped so it can't close a script tag)."""
    payload = build_chart_payload(dto, theme)
    return json.dumps(payload, ensure_ascii=False, default=_json_default).replace("</", "<\\/")


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def to_table(dto: ChartDataDTO) -> tuple[list[str], list[list[str]]]:
    """Accessible tabular alternative: (headers, rows) from categories × series."""
    headers = ["Categoría"] + [s.name for s in dto.series]
    rows: list[list[str]] = []
    for i, category in enumerate(dto.categories):
        row = [category]
        for series in dto.series:
            value = series.data[i] if i < len(series.data) else None
            row.append("—" if value is None else _format_value(value, dto.unit))
        rows.append(row)
    return headers, rows


def _format_value(value: float, unit: str | None) -> str:
    text = f"{value:,.2f}".rstrip("0").rstrip(".") if value % 1 else f"{int(value):,}"
    return f"{text} {unit}" if unit else text
