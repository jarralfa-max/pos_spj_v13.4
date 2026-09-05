"""Enums for the ForecastingPlatform (§16-25, BI-7)."""

from __future__ import annotations

from enum import Enum


class ForecastModelFamily(str, Enum):
    """§19 — extensible; no single algorithm is depended on. The four
    marked (BI-9) are the baseline set BI-9 actually implements; the rest
    are reserved vocabulary for later stages so `ForecastModelDefinition`
    never needs a breaking enum change to adopt them."""
    NAIVE = "NAIVE"                                    # BI-9
    SEASONAL_NAIVE = "SEASONAL_NAIVE"                   # BI-9
    MOVING_AVERAGE = "MOVING_AVERAGE"                   # BI-9
    WEIGHTED_MOVING_AVERAGE = "WEIGHTED_MOVING_AVERAGE"  # BI-9
    SES = "SES"                                         # BI-9
    HOLT = "HOLT"                                       # BI-9
    HOLT_WINTERS = "HOLT_WINTERS"                       # BI-9
    ARIMA = "ARIMA"                                     # future stage
    SARIMA = "SARIMA"                                   # future stage
    ETS = "ETS"                                         # future stage
    GRADIENT_BOOSTED_TREES = "GRADIENT_BOOSTED_TREES"   # future stage


class ForecastModelStatus(str, Enum):
    """§20 — a model's lifecycle. Champion/challenger (§23) is expressed by
    two models both in ACTIVE-adjacent states, not by this enum alone."""
    DRAFT = "DRAFT"
    TESTING = "TESTING"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    RETIRED = "RETIRED"


class ForecastRunStatus(str, Enum):
    """Mirrors the BI-2 canonical events FORECAST_RUN_STARTED/COMPLETED/FAILED."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SafetyStockMethod(str, Enum):
    """§72 — configurable safety-stock methods; the legacy
    `SafetyStockCalculator` (BI-6) only ever had `SERVICE_LEVEL`."""
    FIXED_DAYS = "FIXED_DAYS"
    SERVICE_LEVEL = "SERVICE_LEVEL"
    DEMAND_VARIABILITY = "DEMAND_VARIABILITY"
    CUSTOM = "CUSTOM"


class RecommendationPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EstimateConfidence(str, Enum):
    """§35 — a statistical estimate's reliability, distinct from the 0..1
    numeric `confidence` used on recommendations: this is qualitative and
    specifically about whether there is *enough data variation* to trust
    the estimate at all, not how strong the signal is once trusted."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class PriceRecommendationType(str, Enum):
    """§33, plus `REVIEW_REQUIRED` (§35 — the explicit fallback when
    elasticity confidence is LOW; not enumerated in §33's list but named
    directly in §35's text)."""
    INCREASE_PRICE = "INCREASE_PRICE"
    DECREASE_PRICE = "DECREASE_PRICE"
    HOLD_PRICE = "HOLD_PRICE"
    PROMOTIONAL_DISCOUNT = "PROMOTIONAL_DISCOUNT"
    CLEARANCE = "CLEARANCE"
    REVIEW_MARGIN = "REVIEW_MARGIN"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
