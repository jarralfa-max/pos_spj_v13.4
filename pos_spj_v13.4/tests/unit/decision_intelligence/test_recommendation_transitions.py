from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.domain.decision_intelligence.enums import (
    BusinessRecommendationType,
    RecommendationStatus,
)
from backend.domain.decision_intelligence.exceptions import (
    InvalidRecommendationTransitionError,
)
from backend.domain.decision_intelligence.services import recommendation_transitions as rt
from backend.domain.decision_intelligence.value_objects.business_recommendation import (
    BusinessRecommendation,
)
from backend.domain.forecasting.enums import RecommendationPriority
from backend.shared.ids import new_uuid


def _make(status=RecommendationStatus.NEW) -> BusinessRecommendation:
    return BusinessRecommendation(
        id=new_uuid(), recommendation_type=BusinessRecommendationType.PURCHASE_MORE,
        target_type="product", target_id="p1", branch_id="b1",
        title="Comprar 20 unidades", summary="Riesgo de quiebre de stock",
        evidence={"suggested_quantity": "20"}, expected_impact="Cobertura de 7 días",
        confidence=Decimal("0.8"), priority=RecommendationPriority.HIGH,
        status=status, valid_from=date(2026, 9, 1), valid_until=date(2026, 9, 8),
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )


def test_full_happy_path_new_to_executed_externally():
    rec = _make()
    rec = rt.acknowledge(rec)
    assert rec.status == RecommendationStatus.ACKNOWLEDGED
    rec = rt.start_review(rec)
    assert rec.status == RecommendationStatus.UNDER_REVIEW
    rec = rt.approve(rec)
    assert rec.status == RecommendationStatus.APPROVED
    rec = rt.mark_executed_externally(rec)
    assert rec.status == RecommendationStatus.EXECUTED_EXTERNALLY
    assert rec.is_terminal()


def test_transition_returns_a_new_instance_not_mutated_in_place():
    original = _make()
    updated = rt.acknowledge(original)
    assert original.status == RecommendationStatus.NEW  # unchanged
    assert updated.status == RecommendationStatus.ACKNOWLEDGED
    assert original is not updated


def test_cannot_approve_directly_from_new():
    rec = _make(status=RecommendationStatus.NEW)
    with pytest.raises(InvalidRecommendationTransitionError):
        rt.approve(rec)


def test_cannot_mark_executed_externally_without_approval():
    rec = _make(status=RecommendationStatus.UNDER_REVIEW)
    with pytest.raises(InvalidRecommendationTransitionError):
        rt.mark_executed_externally(rec)


def test_reject_only_valid_from_under_review():
    rec = _make(status=RecommendationStatus.UNDER_REVIEW)
    rec = rt.reject(rec)
    assert rec.status == RecommendationStatus.REJECTED

    rec2 = _make(status=RecommendationStatus.NEW)
    with pytest.raises(InvalidRecommendationTransitionError):
        rt.reject(rec2)


@pytest.mark.parametrize("status", [
    RecommendationStatus.REJECTED, RecommendationStatus.EXECUTED_EXTERNALLY,
    RecommendationStatus.EXPIRED, RecommendationStatus.DISMISSED,
])
def test_terminal_states_accept_no_further_transitions(status):
    rec = _make(status=status)
    for fn in (rt.acknowledge, rt.start_review, rt.approve, rt.reject, rt.dismiss,
               rt.expire, rt.mark_executed_externally):
        with pytest.raises(InvalidRecommendationTransitionError):
            fn(rec)


def test_dismiss_and_expire_reachable_from_new_and_acknowledged():
    for start_status in (RecommendationStatus.NEW, RecommendationStatus.ACKNOWLEDGED):
        assert rt.dismiss(_make(status=start_status)).status == RecommendationStatus.DISMISSED
        assert rt.expire(_make(status=start_status)).status == RecommendationStatus.EXPIRED
