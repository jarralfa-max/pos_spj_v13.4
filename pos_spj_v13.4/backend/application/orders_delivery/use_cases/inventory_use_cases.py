"""Inventory reservation use cases (master prompt §23-24). Orders/Delivery
never writes Inventory's tables directly — every line reservation goes
through `OrdersDeliveryInventoryClient`, which calls Inventory's own
already-migrated `CreateReservationUseCase`/`ReleaseReservationUseCase`.

Reuses `ORDER_CONFIRM`/`ORDER_CANCEL` rather than minting new "reserva.*"
permissions — reservation is the automatic side effect of confirming an
order (§17's flow: confirmar → reservar), not a distinct user-facing action,
same reasoning ORD-6 already applied to schedule activation.

Scope note (see `docs/refactor/ORD-8_inventario.md`): Allocation (binding a
reservation to specific lots, §23's "asignación de lote") and Commit
(converting a reservation into an actual stock decrement using
`final_quantity`/`final_weight`, §50) are deliberately NOT built here —
Commit needs `final_quantity`/`final_weight`, which only exist after
catch-weight adjustment (ORD-10). Building it now would mean committing
against `requested_quantity`, which master prompt §50 explicitly forbids
once an adjustment has happened.
"""

from __future__ import annotations

from backend.application.orders_delivery.dto import CustomerOrderDTO
from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions
from backend.application.orders_delivery.result import OrderResult, fail_from_domain_error
from backend.application.orders_delivery.use_cases._base import _OrdersDeliveryBaseUseCase
from backend.domain.orders_delivery.events import OrderEvents
from backend.domain.orders_delivery.exceptions import (
    OrderInventoryReservationFailedError,
    OrderNotFoundError,
    OrdersDeliveryDomainError,
)
from backend.infrastructure.db.repositories.orders_delivery.unit_of_work import (
    OrdersDeliveryUnitOfWork,
)
from backend.infrastructure.integrations.orders_delivery_inventory_client import (
    OrdersDeliveryInventoryClient,
)


class ReserveOrderInventoryUseCase(_OrdersDeliveryBaseUseCase):
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

            client = OrdersDeliveryInventoryClient(connection, branch_id=order.branch_id)
            reserved: list[tuple] = []  # (line, reservation_id) — for compensation on failure
            try:
                for line in order.lines:
                    line_operation_id = f"{operation_id}-{line.id}"
                    quantity = line.requested_quantity.value if line.requested_quantity else 0
                    weight = line.requested_weight.value if line.requested_weight else 0
                    reservation_id = client.reserve_line(
                        product_id=line.product_id, quantity=quantity, weight=weight,
                        order_id=order.id, operation_id=line_operation_id,
                        actor_user_id=actor_user_id)
                    line.set_reservation(reservation_id)
                    reserved.append((line, reservation_id))
                order.mark_reserved()
            except OrderInventoryReservationFailedError as exc:
                for line, reservation_id in reserved:
                    try:
                        client.release(
                            reservation_id, operation_id=f"{operation_id}-release-{line.id}",
                            actor_user_id=actor_user_id, reason="Compensación: reserva parcial fallida")
                    except OrdersDeliveryDomainError:
                        pass  # best-effort compensation; the failed reservation is reported below
                    line.clear_reservation()
                order.mark_reservation_failed()
                uow.orders.save(order)
                self._emit(
                    uow, OrderEvents.RESERVATION_FAILED, aggregate_type="CustomerOrder",
                    entity_id=order.id, operation_id=operation_id, branch_id=order.branch_id,
                    actor_user_id=actor_user_id, reason=str(exc))
                return fail_from_domain_error(exc, operation_id=operation_id)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)

            uow.orders.save(order)
            self._emit(
                uow, OrderEvents.RESERVED, aggregate_type="CustomerOrder", entity_id=order.id,
                operation_id=operation_id, branch_id=order.branch_id, actor_user_id=actor_user_id)
        return OrderResult.ok(
            "Inventario reservado", entity_id=order.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(order))


class ReleaseOrderInventoryUseCase(_OrdersDeliveryBaseUseCase):
    def execute(self, connection, *, order_id: str, actor_user_id: str, operation_id: str,
                reason: str = "") -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.ORDER_CANCEL)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            order = uow.orders.get(order_id)
            if order is None:
                return fail_from_domain_error(
                    OrderNotFoundError(f"Pedido {order_id} no existe"), operation_id=operation_id)

            client = OrdersDeliveryInventoryClient(connection, branch_id=order.branch_id)
            try:
                for line in order.lines:
                    if not line.inventory_reservation_id:
                        continue
                    client.release(
                        line.inventory_reservation_id,
                        operation_id=f"{operation_id}-release-{line.id}",
                        actor_user_id=actor_user_id, reason=reason or "Liberación de reserva")
                    line.clear_reservation()
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)

            uow.orders.save(order)
        return OrderResult.ok(
            "Reserva de inventario liberada", entity_id=order.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(order))
