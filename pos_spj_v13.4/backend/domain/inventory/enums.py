"""Canonical enums for the inventory bounded context (INV-1 subset).

Only the security-relevant enums are defined here. Operational enums
(movement types, inventory statuses, transfer/count states, warehouse types …)
are added in INV-2/INV-3 alongside the entities that own them.
"""

from __future__ import annotations

from enum import Enum


class LimitDecision(str, Enum):
    """Outcome of evaluating an operation value against a configured limit."""

    WITHIN = "WITHIN"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"
    EXCEEDS = "EXCEEDS"


class LimitBasis(str, Enum):
    """What the limit thresholds are measured in (informational)."""

    QUANTITY = "QUANTITY"
    WEIGHT = "WEIGHT"
    VALUE = "VALUE"
    VARIANCE_PCT = "VARIANCE_PCT"


class InventoryDuty(str, Enum):
    """Distinct duties that segregation of duties keeps in separate hands (§47)."""

    WAREHOUSE_CLERK = "WAREHOUSE_CLERK"
    WAREHOUSE_SUPERVISOR = "WAREHOUSE_SUPERVISOR"
    RECEIVER = "RECEIVER"
    DISPATCHER = "DISPATCHER"
    PHYSICAL_COUNTER = "PHYSICAL_COUNTER"
    ADJUSTMENT_APPROVER = "ADJUSTMENT_APPROVER"
    QUALITY = "QUALITY"
    AUDITOR = "AUDITOR"
    CONFIG_ADMIN = "CONFIG_ADMIN"
