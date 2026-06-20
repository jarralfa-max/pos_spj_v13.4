"""Delivery view DTOs — read-only data carriers from QueryService to UI.

All fields use canonical types. Spanish labels are resolved here so the UI
never touches raw enum values or status strings.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from core.delivery.domain.value_objects import (
    DeliveryAction,
    DeliveryStatus,
    FulfillmentType,
    PaymentStatus,
    STATUS_LABELS_ES,
    UNIT_LABELS_ES,
    UnitCode,
    WEIGHABLE_UNITS,
)


@dataclass(frozen=True)
class DeliveryItemViewDTO:
    """Read-only view of a single line item inside a delivery order."""

    item_id: str
    product_id: str
    product_name: str
    requested_quantity: Decimal
    actual_quantity: Decimal | None
    unit_code: UnitCode
    unit_label_es: str               # resolved from UNIT_LABELS_ES
    allows_weight_adjustment: bool   # True if unit is in WEIGHABLE_UNITS
    available_stock: Decimal


@dataclass(frozen=True)
class DeliveryOrderViewDTO:
    """Read-only view of a delivery order including available actions."""

    order_id: str
    folio: str
    branch_id: str
    customer_name: str
    customer_tel: str
    fulfillment_type: FulfillmentType
    status: DeliveryStatus
    status_label_es: str             # resolved from STATUS_LABELS_ES
    payment_status: PaymentStatus
    driver_id: str | None
    driver_name: str | None
    items: tuple[DeliveryItemViewDTO, ...]
    available_actions: tuple[DeliveryAction, ...]
    created_at: str
    total: Decimal
    # ── Operational fields consumed by the board presenters (Kanban + list) ──
    # These keep the canonical route lossless: every datum the UI renders comes
    # from this single DTO, never from a second query.
    direccion: str = ""
    workflow_type: str = ""
    scheduled_at: str = ""
    source: str = ""
    adjustment_pending: bool = False
    status_legacy: str = ""          # raw normalized DB status (tab/column filters)
