import sqlite3
from datetime import date, datetime
from decimal import Decimal

import pytest

from backend.domain.decision_intelligence.enums import (
    BusinessRecommendationType,
    RecommendationStatus,
)
from backend.domain.decision_intelligence.value_objects.business_recommendation import (
    BusinessRecommendation,
)
from backend.domain.forecasting.enums import RecommendationPriority
from backend.shared.ids import new_uuid
from frontend.desktop.modules.business_intelligence.presenters.price_recommendation_presenter import (
    PriceRecommendationPresenter,
    RecommendationTransitionError,
    RecommendationUnavailableError,
    map_recommendation_kpis,
)


def _recommendation(**overrides) -> BusinessRecommendation:
    defaults = dict(
        id=new_uuid(), recommendation_type=BusinessRecommendationType.PRICE_DECREASE,
        target_type="product", target_id="p1", branch_id="b1",
        title="t", summary="s", evidence={"current_price": "16"}, expected_impact="i",
        confidence=Decimal("0.8"), priority=RecommendationPriority.MEDIUM,
        status=RecommendationStatus.NEW, valid_from=date(2026, 1, 1),
        valid_until=date(2026, 2, 1), created_at=datetime(2026, 1, 1),
    )
    defaults.update(overrides)
    return BusinessRecommendation(**defaults)


def test_map_recommendation_kpis_reports_type_priority_confidence_status():
    rec = _recommendation()
    by_key = {c.key: c for c in map_recommendation_kpis(rec)}
    assert by_key["type"].value == "PRICE_DECREASE"
    assert by_key["priority"].value == "MEDIUM"
    assert by_key["confidence"].value == "80%"
    assert by_key["status"].value == "NEW"
    assert by_key["status"].variant == "neutral"


def test_map_recommendation_kpis_marks_approved_status_success():
    rec = _recommendation(status=RecommendationStatus.APPROVED)
    assert map_recommendation_kpis(rec)[3].variant == "success"


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
    presenter = PriceRecommendationPresenter(conn)
    assert presenter.search_products("res") == []
    assert presenter.search_branches("centro") == []


def test_generate_requires_a_product_id(conn):
    presenter = PriceRecommendationPresenter(conn)
    with pytest.raises(RecommendationUnavailableError):
        presenter.generate(product_id="", branch_id="b1",
                            margin_review_threshold_pct=10.0, valid_for_days=30)


def test_generate_requires_a_branch_id(conn):
    presenter = PriceRecommendationPresenter(conn)
    with pytest.raises(RecommendationUnavailableError):
        presenter.generate(product_id="p1", branch_id="",
                            margin_review_threshold_pct=10.0, valid_for_days=30)


def test_generate_requires_a_positive_validity_window(conn):
    presenter = PriceRecommendationPresenter(conn)
    with pytest.raises(RecommendationUnavailableError):
        presenter.generate(product_id="p1", branch_id="b1",
                            margin_review_threshold_pct=10.0, valid_for_days=0)


def test_generate_with_no_sales_history_raises_unavailable(conn):
    presenter = PriceRecommendationPresenter(conn)
    with pytest.raises(RecommendationUnavailableError):
        presenter.generate(product_id="p1", branch_id="b1",
                            margin_review_threshold_pct=10.0, valid_for_days=30)


def test_generate_with_a_single_price_point_is_informational_only(conn):
    """Only one distinct price ever sold at: `estimate_price_elasticity`
    can't estimate anything (needs >= 2 distinct prices), so the pricing
    decision is REVIEW_REQUIRED — informational, not promoted to a
    BusinessRecommendation (§39)."""
    _sale(conn, day="2026-01-01", price=10, qty=50)
    conn.commit()
    presenter = PriceRecommendationPresenter(conn)
    recommendation, price_rec, message = presenter.generate(
        product_id="p1", branch_id="b1", margin_review_threshold_pct=10.0, valid_for_days=30)
    assert recommendation is None
    assert price_rec.recommendation_type.value == "REVIEW_REQUIRED"
    assert message


def test_generate_with_elastic_demand_history_produces_a_real_decrease_recommendation(conn):
    """q = 1024/price^2 across 5 distinct prices is a textbook elastic
    demand curve (elasticity exactly -2, same construction BI-16's own
    elasticity test uses) — well past the -1.5 elastic threshold, so the
    real decision is DECREASE_PRICE, which DOES get promoted to a
    BusinessRecommendation."""
    for day, price, qty in [
        ("2026-01-01", 1, 1024), ("2026-01-02", 2, 256), ("2026-01-03", 4, 64),
        ("2026-01-04", 8, 16), ("2026-01-05", 16, 4),
    ]:
        _sale(conn, day=day, price=price, qty=qty)
    conn.commit()

    presenter = PriceRecommendationPresenter(conn)
    recommendation, price_rec, message = presenter.generate(
        product_id="p1", branch_id="b1", margin_review_threshold_pct=10.0, valid_for_days=30)
    assert message is None
    assert recommendation is not None
    assert recommendation.recommendation_type.value == "PRICE_DECREASE"
    assert recommendation.status.value == "NEW"
    assert recommendation.branch_id == "b1"

    acknowledged = presenter.apply_transition(recommendation, "acknowledge")
    assert acknowledged.status.value == "ACKNOWLEDGED"
    under_review = presenter.apply_transition(acknowledged, "start_review")
    assert under_review.status.value == "UNDER_REVIEW"
    approved = presenter.apply_transition(under_review, "approve")
    assert approved.status.value == "APPROVED"


def test_apply_transition_rejects_an_invalid_jump(conn):
    presenter = PriceRecommendationPresenter(conn)
    rec = _recommendation()  # status=NEW
    with pytest.raises(RecommendationTransitionError):
        presenter.apply_transition(rec, "approve")  # NEW -> APPROVED is not allowed


def test_apply_transition_rejects_an_unknown_action(conn):
    presenter = PriceRecommendationPresenter(conn)
    rec = _recommendation()
    with pytest.raises(RecommendationTransitionError):
        presenter.apply_transition(rec, "not_a_real_action")
