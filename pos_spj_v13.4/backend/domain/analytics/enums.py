"""Enums for the Semantic Metrics Layer (BI-3, master-prompt §11-12/§62/§65)."""

from __future__ import annotations

from enum import Enum


class AggregationType(str, Enum):
    SUM = "SUM"
    AVG = "AVG"
    COUNT = "COUNT"
    RATIO = "RATIO"
    MAX = "MAX"
    MIN = "MIN"
    CUSTOM = "CUSTOM"


class TimeGrain(str, Enum):
    HOURLY = "HOURLY"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


class CurrencyBehavior(str, Enum):
    """Whether a metric's value is money, a ratio, or a plain count — §130-131:
    money must never be treated as a plain float downstream."""
    NONE = "NONE"
    MONETARY = "MONETARY"
    PERCENTAGE = "PERCENTAGE"


class ScopePolicy(str, Enum):
    """§62/§116 — analytical scope a metric/recommendation/alert can be
    evaluated at. QueryServices apply this; hiding a section in the UI is
    not enforcement."""
    OWN = "OWN"
    TEAM = "TEAM"
    BRANCH = "BRANCH"
    TERRITORY = "TERRITORY"
    REGION = "REGION"
    COMPANY = "COMPANY"
    ALL = "ALL"


class FreshnessPolicy(str, Enum):
    """§65 — how current a metric's underlying data is expected to be."""
    LIVE = "LIVE"
    NEAR_REAL_TIME = "NEAR_REAL_TIME"
    LAST_SYNC = "LAST_SYNC"
    DAILY = "DAILY"
    STALE = "STALE"
