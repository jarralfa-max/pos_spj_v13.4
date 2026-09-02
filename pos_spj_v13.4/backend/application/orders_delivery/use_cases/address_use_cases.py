"""SetOrderDeliveryAddressUseCase (master prompt §20-22): captures/replaces
an order's delivery address, resolves the matching `DeliveryZone` by postal
code, and sets `CustomerOrder.delivery_fee` from `DeliveryFeePolicy` — the
one place a delivery fee is ever assigned (never a UI-side computation).

Gated by `ORDER_EDIT_DRAFT` — no dedicated "direccion.*" permission exists
(the master prompt's own §63 permission list doesn't define one either);
setting the delivery address is part of editing the order while still
mutable, same tier as adding/removing lines.
"""

from __future__ import annotations

from backend.application.orders_delivery.dto import CustomerOrderDTO
from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions
from backend.application.orders_delivery.result import OrderResult, fail_from_domain_error
from backend.application.orders_delivery.use_cases._base import _OrdersDeliveryBaseUseCase
from backend.domain.orders_delivery.address import OrderAddress
from backend.domain.orders_delivery.enums import FulfillmentType
from backend.domain.orders_delivery.exceptions import OrderNotFoundError, OrdersDeliveryDomainError
from backend.domain.orders_delivery.policies.delivery_fee_policy import DeliveryFeePolicy
from backend.infrastructure.db.repositories.orders_delivery.unit_of_work import (
    OrdersDeliveryUnitOfWork,
)

_ZONE_REQUIRED_FULFILLMENT_TYPES = frozenset({
    FulfillmentType.HOME_DELIVERY, FulfillmentType.BRANCH_DELIVERY,
    FulfillmentType.WHOLESALE_DELIVERY, FulfillmentType.SCHEDULED_DELIVERY,
    FulfillmentType.EXPRESS_DELIVERY, FulfillmentType.ROUTE_DELIVERY,
})


class SetOrderDeliveryAddressUseCase(_OrdersDeliveryBaseUseCase):
    def execute(
        self, connection, *, order_id: str, recipient_name: str, recipient_phone: str,
        street: str, exterior_number: str, actor_user_id: str, operation_id: str,
        interior_number: str | None = None, neighborhood: str | None = None,
        postal_code: str | None = None, municipality: str | None = None,
        state: str | None = None, references: str | None = None,
    ) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.ORDER_EDIT_DRAFT)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            order = uow.orders.get(order_id)
            if order is None:
                return fail_from_domain_error(
                    OrderNotFoundError(f"Pedido {order_id} no existe"), operation_id=operation_id)
            try:
                address = OrderAddress.create(
                    order_id=order_id, recipient_name=recipient_name,
                    recipient_phone=recipient_phone, street=street,
                    exterior_number=exterior_number, interior_number=interior_number,
                    neighborhood=neighborhood, postal_code=postal_code,
                    municipality=municipality, state=state, references=references,
                )
                if order.fulfillment_type in _ZONE_REQUIRED_FULFILLMENT_TYPES:
                    zones = uow.zones.list_active_for_branch(order.branch_id)
                    zone = DeliveryFeePolicy.resolve_zone(zones, postal_code=postal_code or "")
                    address.assign_zone(zone.id)
                    fee = DeliveryFeePolicy.calculate_fee(zone, order_subtotal=order.totals.subtotal)
                    order.set_delivery_fee(fee)
                order.set_delivery_address(address.id)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)

            uow.addresses.save(address)
            uow.orders.save(order)
        return OrderResult.ok(
            "Dirección de entrega registrada", entity_id=order.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(order), address_id=address.id)
