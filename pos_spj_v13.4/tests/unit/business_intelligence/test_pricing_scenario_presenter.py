import sqlite3
from datetime import datetime
from decimal import Decimal

import pytest

from backend.domain.scenario_planning.value_objects.scenario import ScenarioResult
from backend.shared.ids import new_uuid
from frontend.desktop.modules.business_intelligence.presenters.pricing_scenario_presenter import (
    PricingScenarioPresenter,
    ScenarioUnavailableError,
    map_scenario_kpis,
)


def _result(**overrides) -> ScenarioResult:
    defaults = dict(
        scenario_id=new_uuid(),
        baseline_metrics={"price": Decimal("10"), "expected_volume_change_pct": Decimal("0"),
                           "expected_revenue_change_pct": Decimal("0")},
        scenario_metrics={"price": Decimal("9.5"), "expected_volume_change_pct": Decimal("12.5"),
                           "expected_revenue_change_pct": Decimal("6.9")},
        evaluated_at=datetime(2026, 1, 1),
    )
    defaults.update(overrides)
    return ScenarioResult(**defaults)


def test_map_scenario_kpis_reports_price_and_deltas():
    result = _result()
    by_key = {c.key: c for c in map_scenario_kpis(result)}
    assert by_key["price"].value == "$9.50"
    assert by_key["expected_volume_change_pct"].value == "+12.5%"
    assert by_key["expected_volume_change_pct"].variant == "success"
    assert by_key["expected_revenue_change_pct"].value == "+6.9%"
    assert "expected_margin_change_pct" not in by_key


def test_map_scenario_kpis_marks_negative_deltas_as_danger():
    result = _result(scenario_metrics={
        "price": Decimal("11"), "expected_volume_change_pct": Decimal("-5"),
        "expected_revenue_change_pct": Decimal("-2"),
    })
    by_key = {c.key: c for c in map_scenario_kpis(result)}
    assert by_key["expected_volume_change_pct"].variant == "danger"


def test_map_scenario_kpis_includes_margin_when_present():
    result = _result(
        baseline_metrics={**_result().baseline_metrics, "expected_margin_change_pct": Decimal("0")},
        scenario_metrics={**_result().scenario_metrics, "expected_margin_change_pct": Decimal("3.2")},
    )
    by_key = {c.key: c for c in map_scenario_kpis(result)}
    assert by_key["expected_margin_change_pct"].value == "+3.2%"


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE ventas (id TEXT PRIMARY KEY, estado TEXT, fecha TEXT, sucursal_id TEXT)")
    connection.execute(
        "CREATE TABLE detalles_venta (id TEXT PRIMARY KEY, venta_id TEXT, producto_id TEXT, "
        "cantidad REAL, precio_unitario REAL)")
    connection.execute(
        "CREATE TABLE products (id TEXT PRIMARY KEY, code TEXT, name TEXT, short_name TEXT, "
        "product_type TEXT, base_unit_id TEXT, species_id TEXT, catch_weight_enabled INTEGER, "
        "lot_controlled INTEGER, inventory_managed INTEGER, sellable INTEGER, "
        "purchasable INTEGER, producible INTEGER, internal_only INTEGER, "
        "lifecycle_status TEXT)")
    connection.execute("CREATE TABLE sucursales (id TEXT PRIMARY KEY, nombre TEXT, activa INTEGER)")
    connection.execute(
        "CREATE TABLE product_cost (product_id TEXT, branch_id TEXT, average_cost REAL)")
    yield connection
    connection.close()


def _sale(conn, *, day, price, qty, product_id="p1", branch_id="b1"):
    sale_id = new_uuid()
    conn.execute("INSERT INTO ventas (id, estado, fecha, sucursal_id) VALUES (?,?,?,?)",
                 (sale_id, "completada", f"{day} 10:00:00", branch_id))
    conn.execute(
        "INSERT INTO detalles_venta (id, venta_id, producto_id, cantidad, precio_unitario) "
        "VALUES (?,?,?,?,?)", (new_uuid(), sale_id, product_id, qty, price))


def test_search_products_and_branches_degrade_gracefully_with_no_rows(conn):
    presenter = PricingScenarioPresenter(conn)
    assert presenter.search_products("res") == []
    assert presenter.search_branches("centro") == []


def test_simulate_requires_a_product_id(conn):
    presenter = PricingScenarioPresenter(conn)
    with pytest.raises(ScenarioUnavailableError):
        presenter.simulate(product_id="", branch_id="b1", price_change_pct=-10.0)


def test_simulate_requires_a_branch_id(conn):
    presenter = PricingScenarioPresenter(conn)
    with pytest.raises(ScenarioUnavailableError):
        presenter.simulate(product_id="p1", branch_id="", price_change_pct=-10.0)


def test_simulate_requires_a_nonzero_price_change(conn):
    presenter = PricingScenarioPresenter(conn)
    with pytest.raises(ScenarioUnavailableError):
        presenter.simulate(product_id="p1", branch_id="b1", price_change_pct=0.0)


def test_simulate_with_no_sales_history_raises_unavailable(conn):
    presenter = PricingScenarioPresenter(conn)
    with pytest.raises(ScenarioUnavailableError):
        presenter.simulate(product_id="p1", branch_id="b1", price_change_pct=-10.0)


def test_simulate_with_a_single_price_point_raises_insufficient_elasticity(conn):
    """Only one distinct price ever sold at: `estimate_price_elasticity`
    returns LOW confidence (needs >= 2 distinct prices), which
    `PricingWhatIfService` refuses to simulate against (§35) — a readable
    error, not a stack trace."""
    _sale(conn, day="2026-01-01", price=10, qty=50)
    conn.commit()
    presenter = PricingScenarioPresenter(conn)
    with pytest.raises(ScenarioUnavailableError):
        presenter.simulate(product_id="p1", branch_id="b1", price_change_pct=-10.0)


def test_simulate_with_elastic_demand_history_produces_a_real_scenario_result(conn):
    """Same q=1024/price^2 elastic-demand construction as BI-27's own test
    (elasticity exactly -2) — proves the real PricingWhatIfService runs
    end-to-end against real sales history, not a mock."""
    for day, price, qty in [
        ("2026-01-01", 1, 1024), ("2026-01-02", 2, 256), ("2026-01-03", 4, 64),
        ("2026-01-04", 8, 16), ("2026-01-05", 16, 4),
    ]:
        _sale(conn, day=day, price=price, qty=qty)
    conn.commit()

    presenter = PricingScenarioPresenter(conn)
    result = presenter.simulate(product_id="p1", branch_id="b1", price_change_pct=-10.0)
    assert result.scenario_metrics["price"] == Decimal("16") * Decimal("0.9")
    assert result.baseline_metrics["price"] == Decimal("16")
