"""DeliveryActionPolicy — single source of truth for available UI actions.

Both Kanban cards and the List detail panel use this class to determine
which buttons to render. Never duplicate this logic in the UI layer.
"""
from __future__ import annotations

from core.delivery.domain.value_objects import (
    DeliveryAction,
    DeliveryStatus,
    FulfillmentType,
    PaymentStatus,
)


class DeliveryActionPolicy:
    """Determines available actions for an order given its current state."""

    def available_actions(
        self,
        status: DeliveryStatus,
        fulfillment_type: FulfillmentType,
        payment_status: PaymentStatus,
        has_driver: bool,
    ) -> tuple[DeliveryAction, ...]:
        """Return the ordered tuple of actions available for this order state.

        This is the single source of truth — Kanban and List views must both
        call this method and render buttons from its result.
        """
        actions: list[DeliveryAction] = []

        if status == DeliveryStatus.PENDING:
            actions = [DeliveryAction.START_PREPARATION, DeliveryAction.CANCEL]

        elif status == DeliveryStatus.PREPARING:
            actions = [DeliveryAction.ADJUST_ITEM, DeliveryAction.CONFIRM_PREPARATION]
            # Assign driver early if delivery type and not yet assigned
            if fulfillment_type == FulfillmentType.DELIVERY and not has_driver:
                actions.append(DeliveryAction.ASSIGN_DRIVER)
            actions.append(DeliveryAction.CANCEL)

        elif status == DeliveryStatus.READY_FOR_PICKUP:
            actions = [
                DeliveryAction.COMPLETE_DELIVERY,
                DeliveryAction.SEND_PAYMENT_LINK,
                DeliveryAction.CANCEL,
            ]

        elif status == DeliveryStatus.READY_FOR_DISPATCH:
            actions = [
                DeliveryAction.ASSIGN_DRIVER,
                DeliveryAction.SEND_PAYMENT_LINK,
                DeliveryAction.CANCEL,
            ]

        elif status == DeliveryStatus.ASSIGNED:
            actions = [
                DeliveryAction.START_ROUTE,
                DeliveryAction.SEND_PAYMENT_LINK,
                DeliveryAction.CANCEL,
            ]

        elif status == DeliveryStatus.IN_TRANSIT:
            actions = [
                DeliveryAction.COMPLETE_DELIVERY,
                DeliveryAction.SEND_PAYMENT_LINK,
            ]

        elif status == DeliveryStatus.DELIVERED:
            actions = [
                DeliveryAction.VIEW_DETAIL,
                DeliveryAction.PRINT_TICKET,
                DeliveryAction.RESEND_RECEIPT,
            ]

        elif status == DeliveryStatus.CANCELLED:
            actions = [DeliveryAction.VIEW_DETAIL]

        return tuple(actions)
