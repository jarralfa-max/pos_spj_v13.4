"""Order capture use cases (master prompt §17 flow: capturar → confirmar →
reservar; §18 deduplication). These are the first real callers of
`OrdersDeliveryAuthorizationPolicy.require()` — ORD-1 deliberately left the
policy unwired, `docs/refactor/ORD-1_seguridad.md`'s own "pendiente" section
named this exact phase as the one that would wire it.

Channel-agnostic on purpose (master prompt §1: "No crear sistemas paralelos
para pedidos POS / pedidos WhatsApp / ... — todos deben usar el mismo núcleo
de pedido"): POS, WhatsApp, Counter, Backoffice and API capture all call this
SAME `CreateCustomerOrderUseCase` with a different `channel`/
`external_order_reference`, never a channel-specific create path.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping, Sequence

from backend.application.orders_delivery.dto import CustomerOrderDTO
from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions
from backend.application.orders_delivery.result import OrderResult, fail_from_domain_error
from backend.application.orders_delivery.use_cases._base import _OrdersDeliveryBaseUseCase
from backend.domain.orders_delivery.entities import CustomerOrder, CustomerOrderLine
from backend.domain.orders_delivery.enums import FulfillmentType, OrderChannel, OrderType
from backend.domain.orders_delivery.events import OrderEvents
from backend.domain.orders_delivery.exceptions import OrderNotFoundError, OrdersDeliveryDomainError
from backend.domain.orders_delivery.policies.order_deduplication_policy import (
    OrderDeduplicationPolicy,
)
from backend.domain.orders_delivery.value_objects.order_quantity import OrderQuantity
from backend.infrastructure.db.repositories.orders_delivery.unit_of_work import (
    OrdersDeliveryUnitOfWork,
)


class CreateCustomerOrderUseCase(_OrdersDeliveryBaseUseCase):
    def execute(
        self, connection, *, branch_id: str, channel: OrderChannel | str,
        order_type: OrderType | str, fulfillment_type: FulfillmentType | str,
        lines: Sequence[Mapping[str, Any]], actor_user_id: str, operation_id: str,
        customer_id: str | None = None, contact_name: str | None = None,
        contact_phone: str | None = None,
        external_order_reference: str | None = None,
        whatsapp_order_id: str | None = None,
    ) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.ORDER_CREATE)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        channel = channel if isinstance(channel, OrderChannel) else OrderChannel(channel)
        order_type = order_type if isinstance(order_type, OrderType) else OrderType(order_type)
        fulfillment_type = (fulfillment_type if isinstance(fulfillment_type, FulfillmentType)
                             else FulfillmentType(fulfillment_type))

        with OrdersDeliveryUnitOfWork(connection) as uow:
            existing = OrderDeduplicationPolicy.resolve_existing(
                existing_by_operation_id=uow.orders.find_by_operation_id(operation_id),
                existing_by_channel_reference=(
                    uow.orders.find_by_channel_reference(
                        channel=channel, external_order_reference=external_order_reference)
                    if external_order_reference else None
                ),
            )
            if existing is not None:
                return OrderResult.ok(
                    "Pedido ya existente (idempotente)", entity_id=existing.id,
                    operation_id=operation_id, order=CustomerOrderDTO.from_entity(existing))

            try:
                order = CustomerOrder.create(
                    branch_id=branch_id, channel=channel, order_type=order_type,
                    fulfillment_type=fulfillment_type, customer_id=customer_id,
                    contact_name=contact_name, contact_phone=contact_phone,
                    created_by_user_id=actor_user_id,
                    external_order_reference=external_order_reference,
                    whatsapp_order_id=whatsapp_order_id, operation_id=operation_id,
                )
                for raw_line in lines:
                    order.add_line(_build_line(order.id, raw_line))
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)

            uow.orders.save(order)
            self._emit(
                uow, OrderEvents.CREATED, aggregate_type="CustomerOrder", entity_id=order.id,
                operation_id=operation_id, branch_id=order.branch_id,
                actor_user_id=actor_user_id, channel=channel.value)
        return OrderResult.ok(
            "Pedido creado", entity_id=order.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(order))


class ConfirmCustomerOrderUseCase(_OrdersDeliveryBaseUseCase):
    def execute(self, connection, *, order_id: str, actor_user_id: str,
                operation_id: str) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.ORDER_CONFIRM)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            order = uow.orders.get(order_id)
            if order is None:
                return fail_from_domain_error(
                    OrderNotFoundError(f"Pedido {order_id} no existe"), operation_id=operation_id)
            try:
                order.confirm(confirmed_by_user_id=actor_user_id)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.orders.save(order)
            self._emit(
                uow, OrderEvents.CONFIRMED, aggregate_type="CustomerOrder", entity_id=order.id,
                operation_id=operation_id, branch_id=order.branch_id, actor_user_id=actor_user_id)
        return OrderResult.ok(
            "Pedido confirmado", entity_id=order.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(order))


def _build_line(order_id: str, raw: Mapping[str, Any]) -> CustomerOrderLine:
    def _qty(key: str, unit_key: str) -> OrderQuantity | None:
        value = raw.get(key)
        if value is None:
            return None
        return OrderQuantity(Decimal(str(value)), unit=str(raw.get(unit_key) or "PZA"))

    return CustomerOrderLine.create(
        order_id=order_id, product_id=raw["product_id"],
        unit_price=Decimal(str(raw["unit_price"])),
        variant_id=raw.get("variant_id"),
        requested_quantity=_qty("requested_quantity", "requested_quantity_unit"),
        requested_weight=_qty("requested_weight", "requested_weight_unit"),
        catch_weight_enabled=bool(raw.get("catch_weight_enabled", False)),
        substitution_allowed=bool(raw.get("substitution_allowed", True)),
        customer_notes=raw.get("customer_notes"),
        product_snapshot=raw.get("product_snapshot"),
    )
