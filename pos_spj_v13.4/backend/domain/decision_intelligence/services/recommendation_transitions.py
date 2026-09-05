"""Recommendation lifecycle transitions (§39, BI-18).

`BusinessRecommendation` is frozen — every transition here returns a NEW
instance (via `dataclasses.replace`), never mutates in place, so a
recommendation's history can always be reconstructed from the sequence of
transitions applied to it (same append-only spirit as `ForecastRun`, §69).

`mark_executed_externally()` is the ONLY function that reaches
`EXECUTED_EXTERNALLY` — modeling the rule that BI never marks a
recommendation executed on its own; that status only arrives via an event
from whichever bounded context actually did the purchase/production/price
change/transfer (§39).
"""

from __future__ import annotations

import dataclasses

from backend.domain.decision_intelligence.enums import RecommendationStatus
from backend.domain.decision_intelligence.exceptions import (
    InvalidRecommendationTransitionError,
)
from backend.domain.decision_intelligence.value_objects.business_recommendation import (
    BusinessRecommendation,
)

_ALLOWED_TRANSITIONS: dict[RecommendationStatus, frozenset[RecommendationStatus]] = {
    RecommendationStatus.NEW: frozenset({
        RecommendationStatus.ACKNOWLEDGED, RecommendationStatus.DISMISSED,
        RecommendationStatus.EXPIRED,
    }),
    RecommendationStatus.ACKNOWLEDGED: frozenset({
        RecommendationStatus.UNDER_REVIEW, RecommendationStatus.DISMISSED,
        RecommendationStatus.EXPIRED,
    }),
    RecommendationStatus.UNDER_REVIEW: frozenset({
        RecommendationStatus.APPROVED, RecommendationStatus.REJECTED,
        RecommendationStatus.DISMISSED, RecommendationStatus.EXPIRED,
    }),
    RecommendationStatus.APPROVED: frozenset({
        RecommendationStatus.EXECUTED_EXTERNALLY, RecommendationStatus.EXPIRED,
    }),
    RecommendationStatus.REJECTED: frozenset(),
    RecommendationStatus.EXECUTED_EXTERNALLY: frozenset(),
    RecommendationStatus.EXPIRED: frozenset(),
    RecommendationStatus.DISMISSED: frozenset(),
}


def transition(
    recommendation: BusinessRecommendation, new_status: RecommendationStatus
) -> BusinessRecommendation:
    allowed = _ALLOWED_TRANSITIONS.get(recommendation.status, frozenset())
    if new_status not in allowed:
        raise InvalidRecommendationTransitionError(
            f"Cannot transition BusinessRecommendation from {recommendation.status} "
            f"to {new_status}"
        )
    return dataclasses.replace(recommendation, status=new_status)


def acknowledge(recommendation: BusinessRecommendation) -> BusinessRecommendation:
    return transition(recommendation, RecommendationStatus.ACKNOWLEDGED)


def start_review(recommendation: BusinessRecommendation) -> BusinessRecommendation:
    return transition(recommendation, RecommendationStatus.UNDER_REVIEW)


def approve(recommendation: BusinessRecommendation) -> BusinessRecommendation:
    return transition(recommendation, RecommendationStatus.APPROVED)


def reject(recommendation: BusinessRecommendation) -> BusinessRecommendation:
    return transition(recommendation, RecommendationStatus.REJECTED)


def dismiss(recommendation: BusinessRecommendation) -> BusinessRecommendation:
    return transition(recommendation, RecommendationStatus.DISMISSED)


def expire(recommendation: BusinessRecommendation) -> BusinessRecommendation:
    return transition(recommendation, RecommendationStatus.EXPIRED)


def mark_executed_externally(recommendation: BusinessRecommendation) -> BusinessRecommendation:
    return transition(recommendation, RecommendationStatus.EXECUTED_EXTERNALLY)
