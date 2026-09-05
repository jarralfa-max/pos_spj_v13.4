from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.application.decision_intelligence import adapters
from backend.domain.decision_intelligence.enums import BusinessRecommendationType
from backend.domain.decision_intelligence.exceptions import (
    UnsupportedRecommendationSourceError,
)
from backend.domain.forecasting.enums import PriceRecommendationType, RecommendationPriority
from backend.domain.forecasting.value_objects.branch_recommendation import (
    BranchRecommendation,
    BranchRecommendationType,
    StockTransferRecommendation,
)
from backend.domain.forecasting.value_objects.price_recommendation import PriceRecommendation
from backend.domain.forecasting.value_objects.production_recommendation import (
    ProductionRecommendation,
)
from backend.domain.forecasting.value_objects.purchase_recommendation import (
    PurchaseRecommendation,
)
from backend.shared.ids import new_uuid

_CREATED_AT = datetime(2026, 9, 1, tzinfo=timezone.utc)
_VALID_UNTIL = date(2026, 9, 8)


def test_from_purchase_recommendation():
    source = PurchaseRecommendation(
        id=new_uuid(), product_id="p1", branch_id="b1",
        suggested_quantity=Decimal("20"), coverage_days=Decimal("7"),
        expected_demand=Decimal("70"), current_stock=Decimal("30"),
        incoming_stock=Decimal("0"), safety_stock=Decimal("10"),
        supplier_lead_time_days=3, estimated_cost=Decimal("100"),
        priority=RecommendationPriority.HIGH, confidence=Decimal("0.8"),
        created_at=_CREATED_AT, valid_until=_VALID_UNTIL,
    )
    rec = adapters.from_purchase_recommendation(source)
    assert rec.recommendation_type == BusinessRecommendationType.PURCHASE_MORE
    assert rec.target_type == "product"
    assert rec.target_id == "p1"
    assert rec.branch_id == "b1"
    assert rec.evidence["estimated_cost"] == "100"
    assert rec.priority == RecommendationPriority.HIGH
    assert rec.model_reference == "forecasting.purchase_planning_service"


def test_from_production_recommendation():
    source = ProductionRecommendation(
        id=new_uuid(), product_id="p1", branch_id="b1",
        recommended_production_quantity=Decimal("50"),
        recommended_processing_date=date(2026, 9, 5),
        expected_demand=Decimal("70"), current_stock=Decimal("20"),
        expected_yield_pct=Decimal("0.8"), required_raw_material=Decimal("62.5"),
        capacity_utilization_pct=Decimal("40"), priority=RecommendationPriority.MEDIUM,
        confidence=Decimal("0.7"), created_at=_CREATED_AT, valid_until=_VALID_UNTIL,
    )
    rec = adapters.from_production_recommendation(source)
    assert rec.recommendation_type == BusinessRecommendationType.INCREASE_PRODUCTION
    assert rec.evidence["required_raw_material"] == "62.5"
    assert rec.priority == RecommendationPriority.MEDIUM


def test_from_price_recommendation_increase():
    source = PriceRecommendation(
        id=new_uuid(), product_id="p1", branch_id="b1",
        recommendation_type=PriceRecommendationType.INCREASE_PRICE,
        current_price=Decimal("100"), suggested_price=Decimal("105"),
        expected_volume_change_pct=Decimal("-2.5"), expected_margin_change_pct=Decimal("1"),
        expected_revenue_change_pct=Decimal("2.5"), reason="Demanda inelástica",
        confidence=Decimal("0.9"), created_at=_CREATED_AT, valid_until=_VALID_UNTIL,
    )
    rec = adapters.from_price_recommendation(source)
    assert rec.recommendation_type == BusinessRecommendationType.PRICE_INCREASE
    assert rec.priority == RecommendationPriority.HIGH  # confidence 0.9
    assert rec.summary == "Demanda inelástica"


def test_from_price_recommendation_raises_for_informational_types():
    source = PriceRecommendation(
        id=new_uuid(), product_id="p1", branch_id="b1",
        recommendation_type=PriceRecommendationType.REVIEW_REQUIRED,
        current_price=Decimal("100"), suggested_price=Decimal("100"),
        expected_volume_change_pct=None, expected_margin_change_pct=None,
        expected_revenue_change_pct=None, reason="Historial insuficiente",
        confidence=Decimal("0"), created_at=_CREATED_AT, valid_until=_VALID_UNTIL,
    )
    with pytest.raises(UnsupportedRecommendationSourceError):
        adapters.from_price_recommendation(source)


def test_from_branch_recommendation_increase_stock():
    source = BranchRecommendation(
        id=new_uuid(), branch_id="b1",
        recommendation_type=BranchRecommendationType.INCREASE_STOCK,
        reason="2/3 productos en riesgo", affected_product_ids=("p1", "p2"),
        priority=RecommendationPriority.CRITICAL, confidence=Decimal("0.8"),
        created_at=_CREATED_AT, valid_until=_VALID_UNTIL,
    )
    rec = adapters.from_branch_recommendation(source)
    assert rec.recommendation_type == BusinessRecommendationType.PURCHASE_MORE
    assert rec.target_type == "branch"
    assert rec.evidence["affected_product_count"] == "2"


def test_from_branch_recommendation_raises_for_unmapped_types():
    source = BranchRecommendation(
        id=new_uuid(), branch_id="b1",
        recommendation_type=BranchRecommendationType.CHANGE_ASSORTMENT,
        reason="Surtido subóptimo", affected_product_ids=("p1",),
        priority=RecommendationPriority.LOW, confidence=Decimal("0.5"),
        created_at=_CREATED_AT, valid_until=_VALID_UNTIL,
    )
    with pytest.raises(UnsupportedRecommendationSourceError):
        adapters.from_branch_recommendation(source)


def test_from_stock_transfer_recommendation():
    source = StockTransferRecommendation(
        id=new_uuid(), product_id="p1", source_branch_id="b1", destination_branch_id="b2",
        suggested_quantity=Decimal("210"), priority=RecommendationPriority.HIGH,
        confidence=Decimal("0.8"), created_at=_CREATED_AT, valid_until=_VALID_UNTIL,
    )
    rec = adapters.from_stock_transfer_recommendation(source)
    assert rec.recommendation_type == BusinessRecommendationType.TRANSFER_STOCK
    assert rec.branch_id == "b2"  # destination
    assert rec.evidence["source_branch_id"] == "b1"
