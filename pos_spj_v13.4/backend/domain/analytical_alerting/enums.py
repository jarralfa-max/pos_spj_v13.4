"""Enums for the Alert Engine (§47-50, BI-20)."""

from __future__ import annotations

from enum import Enum


class AlertType(str, Enum):
    """§47 — the 16 canonical alert types."""
    STOCKOUT_RISK = "STOCKOUT_RISK"
    OVERSTOCK = "OVERSTOCK"
    WASTE_SPIKE = "WASTE_SPIKE"
    SALES_DROP = "SALES_DROP"
    SALES_SPIKE = "SALES_SPIKE"
    MARGIN_DROP = "MARGIN_DROP"
    COST_INCREASE = "COST_INCREASE"
    PRICE_ANOMALY = "PRICE_ANOMALY"
    FORECAST_DEVIATION = "FORECAST_DEVIATION"
    PURCHASE_RISK = "PURCHASE_RISK"
    PRODUCTION_SHORTFALL = "PRODUCTION_SHORTFALL"
    BRANCH_UNDERPERFORMANCE = "BRANCH_UNDERPERFORMANCE"
    CASH_RISK = "CASH_RISK"
    CREDIT_RISK = "CREDIT_RISK"
    DATA_QUALITY = "DATA_QUALITY"
    MODEL_DEGRADATION = "MODEL_DEGRADATION"


class AlertSeverity(str, Enum):
    """§48 — configured per rule, never hardcoded per alert type."""
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertStatus(str, Enum):
    """§50."""
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"
    EXPIRED = "EXPIRED"


class Comparison(str, Enum):
    """How an `AnalyticalAlertRule` compares its metric against its
    threshold."""
    GREATER_THAN = "GT"
    GREATER_THAN_OR_EQUAL = "GTE"
    LESS_THAN = "LT"
    LESS_THAN_OR_EQUAL = "LTE"
