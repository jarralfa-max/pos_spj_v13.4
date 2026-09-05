import sqlite3

import pytest

from backend.application.dto.charts.chart_data import ChartType
from frontend.desktop.modules.business_intelligence.presenters.executive_dashboard_presenter import (
    ExecutiveDashboardPresenter,
    _format_kpi_value,
    _format_trend_value,
    _map_chart,
    _map_kpi,
)


def test_format_kpi_value_money():
    assert _format_kpi_value({"value": 1234.5, "unit": "$"}) == "$1,234.50"


def test_format_kpi_value_percent():
    assert _format_kpi_value({"value": 12.34, "unit": "%"}) == "12.3%"


def test_format_kpi_value_plain_count():
    assert _format_kpi_value({"value": 42, "unit": ""}) == "42"


def test_format_trend_value_prefers_delta_pct():
    assert _format_trend_value({"delta_pct": 5.2, "delta_points": 1.0}) == "+5.2%"


def test_format_trend_value_falls_back_to_delta_points():
    assert _format_trend_value({"delta_pct": None, "delta_points": -2.5}) == "-2.5 pts"


def test_format_trend_value_none_when_neither_present():
    assert _format_trend_value({}) is None


def test_map_kpi_maps_semantic_to_variant():
    dto = _map_kpi({"key": "ventas_netas", "title": "Ventas netas", "value": 1000.0,
                    "unit": "$", "semantic": "positive", "direction": "up"})
    assert dto.variant == "success"
    assert dto.trend_direction == "up"
    assert dto.value == "$1,000.00"


def test_map_chart_returns_empty_dto_when_no_data():
    dto = _map_chart("sales_trend", {"kind": "line", "title": "Ventas", "labels": [], "series": []})
    assert dto.is_empty()
    assert dto.chart_type == ChartType.LINE


def test_map_chart_maps_kind_and_series():
    raw = {"kind": "donut", "title": "Métodos de pago", "unit": "$",
           "labels": ["Efectivo", "Tarjeta"],
           "series": [{"name": "Total", "color": "#123", "values": [100, 50]}]}
    dto = _map_chart("payment_methods", raw)
    assert dto.chart_type == ChartType.DONUT
    assert dto.categories == ("Efectivo", "Tarjeta")
    assert dto.series[0].name == "Total"
    assert dto.series[0].data == (100.0, 50.0)


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    yield connection
    connection.close()


def test_presenter_degrades_gracefully_against_a_bare_connection(conn):
    """No schema at all — the underlying Bi*QueryServices already log and
    degrade to empty/zero results per-query (confirmed against real
    behavior, not assumed); the presenter must not crash on top of that."""
    presenter = ExecutiveDashboardPresenter(conn)
    cards = presenter.kpi_cards()
    charts = presenter.charts()
    assert len(cards) <= 6
    assert len(charts) > 0


def test_presenter_caps_kpis_at_six(conn):
    presenter = ExecutiveDashboardPresenter(conn)
    cards = presenter.kpi_cards()
    assert len(cards) <= 6
