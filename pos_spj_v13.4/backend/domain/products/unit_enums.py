"""Unit-of-measure and catch-weight enums for the products bounded context (§12, §15).

PROD-5. Units carry a *dimension* so the conversion policy never mixes weight with
count. Catch-weight products declare a *price basis* (how the real weight becomes
money) — Products defines it; Pricing/POS apply it.
"""

from __future__ import annotations

from enum import Enum


class UnitDimension(str, Enum):
    WEIGHT = "WEIGHT"
    COUNT = "COUNT"
    VOLUME = "VOLUME"
    LENGTH = "LENGTH"
    AREA = "AREA"
    TIME = "TIME"
    PACKAGE = "PACKAGE"
    OTHER = "OTHER"


class PriceBasis(str, Enum):
    """How a catch-weight product turns into money (§12)."""

    PER_KILOGRAM = "PER_KILOGRAM"
    PER_GRAM = "PER_GRAM"
    PER_POUND = "PER_POUND"
    PER_PIECE_WITH_ACTUAL_WEIGHT = "PER_PIECE_WITH_ACTUAL_WEIGHT"
