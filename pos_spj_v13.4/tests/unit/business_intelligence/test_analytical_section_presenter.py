import sqlite3

import pytest

from backend.application.dto.charts.chart_data import ChartType
from frontend.desktop.modules.business_intelligence.presenters.analytical_section_presenter import (
    AnalyticalSectionPresenter,
    _format_mini_value,
    _map_mini_kpi,
    _map_section_chart,
    _map_table,
)


def test_format_mini_value_money():
    assert _format_mini_value({"value": 1234.5, "unit": "$"}) == "$1,234.50"


def test_format_mini_value_percent():
    assert _format_mini_value({"value": 12.34, "unit": "%"}) == "12.3%"


def test_format_mini_value_plain_count():
    assert _format_mini_value({"value": 42, "unit": ""}) == "42"


def test_map_mini_kpi_uses_raw_variant_directly():
    dto = _map_mini_kpi(0, {"title": "Inventario valorizado", "value": 500.0,
                             "unit": "$", "icon": "", "variant": "info"})
    assert dto.key == "kpi_0"
    assert dto.variant == "info"
    assert dto.value == "$500.00"


def test_map_mini_kpi_falls_back_to_neutral_for_unknown_variant():
    dto = _map_mini_kpi(1, {"title": "X", "value": 1, "unit": "", "variant": "not_a_variant"})
    assert dto.variant == "neutral"


def test_map_section_chart_returns_empty_dto_when_no_data():
    dto = _map_section_chart(0, {"kind": "bar", "title": "Merma por categoría",
                                  "labels": [], "series": []})
    assert dto.is_empty()
    assert dto.chart_type == ChartType.BAR


def test_map_section_chart_preserves_none_gap_values():
    raw = {"kind": "line", "title": "X", "labels": ["a", "b"],
           "series": [{"name": "s", "values": [1.0, None]}]}
    dto = _map_section_chart(0, raw)
    assert dto.series[0].data == (1.0, None)


def test_map_table_builds_columns_and_string_rows():
    raw = {"title": "Stock crítico", "columns": ["Producto", "Existencia"],
           "rows": [["Res Molida", 3.5], ["Pollo", None]]}
    dto = _map_table(raw)
    assert [c.title for c in dto.columns] == ["Producto", "Existencia"]
    assert dto.rows == (("Res Molida", "3.5"), ("Pollo", ""))


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    yield connection
    connection.close()


@pytest.mark.parametrize("section_key", ["ventas", "inventario", "compras", "finanzas"])
def test_presenter_degrades_gracefully_against_a_bare_connection(conn, section_key):
    """Same real `BiDashboardService` used by BI-24, just asking for one
    section's tab payload instead of the whole dashboard — no schema at all,
    must not crash."""
    presenter = AnalyticalSectionPresenter(conn, section_key)
    cards = presenter.kpi_cards()
    charts = presenter.charts()
    tables = presenter.tables()
    assert isinstance(cards, list)
    assert isinstance(charts, list)
    assert isinstance(tables, list)


def test_presenter_caches_data_until_invalidated(conn):
    presenter = AnalyticalSectionPresenter(conn, "ventas")
    first = presenter._data()
    assert presenter._data() is first
    presenter.invalidate()
    assert presenter._data() is not first
