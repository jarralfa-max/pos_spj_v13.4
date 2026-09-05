from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.domain.forecasting.enums import RecommendationPriority
from backend.domain.forecasting.value_objects.branch_recommendation import (
    BranchRecommendation,
    BranchRecommendationType,
    StockTransferRecommendation,
)
from backend.shared.ids import new_uuid


def _branch_rec(**overrides) -> BranchRecommendation:
    fields = dict(
        id=new_uuid(), branch_id="b1",
        recommendation_type=BranchRecommendationType.INCREASE_STOCK,
        reason="2/3 productos en riesgo", affected_product_ids=("p1", "p2"),
        priority=RecommendationPriority.HIGH, confidence=Decimal("0.8"),
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc), valid_until=date(2026, 9, 8),
    )
    fields.update(overrides)
    return BranchRecommendation(**fields)


def test_valid_branch_recommendation_constructs():
    rec = _branch_rec()
    assert rec.recommendation_type == BranchRecommendationType.INCREASE_STOCK


def test_rejects_empty_affected_products():
    with pytest.raises(ValueError):
        _branch_rec(affected_product_ids=())


def test_rejects_empty_reason():
    with pytest.raises(ValueError):
        _branch_rec(reason="")


def _transfer_rec(**overrides) -> StockTransferRecommendation:
    fields = dict(
        id=new_uuid(), product_id="p1", source_branch_id="b1", destination_branch_id="b2",
        suggested_quantity=Decimal("50"), priority=RecommendationPriority.MEDIUM,
        confidence=Decimal("0.7"), created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        valid_until=date(2026, 9, 8),
    )
    fields.update(overrides)
    return StockTransferRecommendation(**fields)


def test_valid_transfer_recommendation_constructs():
    rec = _transfer_rec()
    assert rec.suggested_quantity == Decimal("50")


def test_rejects_same_source_and_destination():
    with pytest.raises(ValueError):
        _transfer_rec(source_branch_id="b1", destination_branch_id="b1")


def test_rejects_non_positive_quantity():
    with pytest.raises(ValueError):
        _transfer_rec(suggested_quantity=Decimal("0"))
