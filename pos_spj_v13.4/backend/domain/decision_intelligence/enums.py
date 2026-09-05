"""Enums for the Decision Intelligence engine (§37-39, BI-18)."""

from __future__ import annotations

from enum import Enum


class BusinessRecommendationType(str, Enum):
    """§38 — the 16 canonical recommendation types. Each maps from exactly
    one forecasting-domain source type (see
    `backend/application/decision_intelligence/adapters.py`)."""
    PRICE_INCREASE = "PRICE_INCREASE"
    PRICE_DECREASE = "PRICE_DECREASE"
    PURCHASE_MORE = "PURCHASE_MORE"
    PURCHASE_LESS = "PURCHASE_LESS"
    TRANSFER_STOCK = "TRANSFER_STOCK"
    INCREASE_PRODUCTION = "INCREASE_PRODUCTION"
    DECREASE_PRODUCTION = "DECREASE_PRODUCTION"
    REDUCE_WASTE = "REDUCE_WASTE"
    REVIEW_SUPPLIER = "REVIEW_SUPPLIER"
    REVIEW_BRANCH = "REVIEW_BRANCH"
    EXPAND_ASSORTMENT = "EXPAND_ASSORTMENT"
    REDUCE_ASSORTMENT = "REDUCE_ASSORTMENT"
    PROMOTION_OPPORTUNITY = "PROMOTION_OPPORTUNITY"
    CASH_RISK = "CASH_RISK"
    CREDIT_RISK = "CREDIT_RISK"
    CAPACITY_RISK = "CAPACITY_RISK"


class RecommendationStatus(str, Enum):
    """§39 — BI never sets EXECUTED_EXTERNALLY itself; that transition only
    happens via `mark_executed_externally()` (recommendation_transitions.py),
    modeling an event received from whichever bounded context actually
    executed the action."""
    NEW = "NEW"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED_EXTERNALLY = "EXECUTED_EXTERNALLY"
    EXPIRED = "EXPIRED"
    DISMISSED = "DISMISSED"
