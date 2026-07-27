"""Delivery workflow policy — maps status transitions per fulfillment type.

This is the single source of truth for what state follows CONFIRM_PREPARATION
and what transitions are allowed per fulfillment type.
"""
from __future__ import annotations

from .value_objects import DeliveryStatus, FulfillmentType


class DeliveryWorkflowPolicy:
    """Defines allowed status transitions per fulfillment type."""

    # Transitions allowed for PICKUP (mostrador) orders
    _PICKUP_TRANSITIONS: dict[DeliveryStatus, list[DeliveryStatus]] = {
        DeliveryStatus.PENDING: [DeliveryStatus.PREPARING, DeliveryStatus.CANCELLED],
        DeliveryStatus.PREPARING: [DeliveryStatus.READY_FOR_PICKUP, DeliveryStatus.CANCELLED],
        DeliveryStatus.READY_FOR_PICKUP: [DeliveryStatus.DELIVERED, DeliveryStatus.CANCELLED],
        DeliveryStatus.DELIVERED: [],
        DeliveryStatus.CANCELLED: [],
    }

    # Transitions allowed for DELIVERY (domicilio) orders
    _DELIVERY_TRANSITIONS: dict[DeliveryStatus, list[DeliveryStatus]] = {
        DeliveryStatus.PENDING: [DeliveryStatus.PREPARING, DeliveryStatus.CANCELLED],
        DeliveryStatus.PREPARING: [DeliveryStatus.READY_FOR_DISPATCH, DeliveryStatus.CANCELLED],
        DeliveryStatus.READY_FOR_DISPATCH: [DeliveryStatus.ASSIGNED, DeliveryStatus.CANCELLED],
        DeliveryStatus.ASSIGNED: [DeliveryStatus.IN_TRANSIT, DeliveryStatus.CANCELLED],
        DeliveryStatus.IN_TRANSIT: [DeliveryStatus.DELIVERED],
        DeliveryStatus.DELIVERED: [],
        DeliveryStatus.CANCELLED: [],
    }

    def next_status_after_confirm_preparation(
        self, fulfillment_type: FulfillmentType
    ) -> DeliveryStatus:
        """Return the status an order transitions to after CONFIRM_PREPARATION."""
        if fulfillment_type == FulfillmentType.PICKUP:
            return DeliveryStatus.READY_FOR_PICKUP
        return DeliveryStatus.READY_FOR_DISPATCH

    def allowed_transitions(
        self, status: DeliveryStatus, fulfillment_type: FulfillmentType
    ) -> list[DeliveryStatus]:
        """Return the list of statuses this order can transition to."""
        if fulfillment_type == FulfillmentType.PICKUP:
            return list(self._PICKUP_TRANSITIONS.get(status, []))
        return list(self._DELIVERY_TRANSITIONS.get(status, []))

    def can_transition(
        self,
        from_status: DeliveryStatus,
        to_status: DeliveryStatus,
        fulfillment_type: FulfillmentType,
    ) -> bool:
        """Return True if the transition is permitted."""
        return to_status in self.allowed_transitions(from_status, fulfillment_type)

    @staticmethod
    def requires_driver(workflow_type: str | None) -> bool:
        """Return True when this workflow type requires a driver assignment."""
        return (workflow_type or "").strip().lower() == FulfillmentType.DELIVERY.value
