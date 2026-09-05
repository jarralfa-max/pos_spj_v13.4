"""Domain exceptions for the decision_intelligence bounded context."""

from __future__ import annotations


class DecisionIntelligenceDomainError(Exception):
    """Base for decision_intelligence rule violations."""


class InvalidRecommendationTransitionError(DecisionIntelligenceDomainError):
    pass


class UnsupportedRecommendationSourceError(DecisionIntelligenceDomainError):
    """Raised when an adapter is asked to convert a source recommendation
    type it does not know how to map to a BusinessRecommendationType."""
