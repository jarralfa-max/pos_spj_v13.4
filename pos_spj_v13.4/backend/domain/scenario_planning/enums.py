"""Enums for scenario planning (§41, BI-19)."""

from __future__ import annotations

from enum import Enum


class ScenarioVariableKind(str, Enum):
    """§41 — the 6 named perturbation types the master prompt lists
    (precio ±%, costo ±%, demanda ±%, lead time +días, capacidad +%,
    merma ±%). Each what-if service only accepts the kinds relevant to it —
    `PricingWhatIfService` uses `PRICE_CHANGE_PCT`, `InventoryWhatIfService`
    uses `DEMAND_CHANGE_PCT`, etc."""
    PRICE_CHANGE_PCT = "PRICE_CHANGE_PCT"
    COST_CHANGE_PCT = "COST_CHANGE_PCT"
    DEMAND_CHANGE_PCT = "DEMAND_CHANGE_PCT"
    LEAD_TIME_CHANGE_DAYS = "LEAD_TIME_CHANGE_DAYS"
    CAPACITY_CHANGE_PCT = "CAPACITY_CHANGE_PCT"
    WASTE_CHANGE_PCT = "WASTE_CHANGE_PCT"
