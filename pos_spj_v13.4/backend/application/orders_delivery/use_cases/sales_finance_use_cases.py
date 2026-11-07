"""Sales/Finance integration use cases (master prompt §22): a CustomerOrder
projects into a commercial `Sale`, payments recorded against that Sale
project back onto the order's own `PaymentStatus`, and a refund reverses
both sides together. Orders/Delivery never writes `sales`/`sale_lines`
directly — every call goes through `OrdersDeliverySalesClient`, same
discipline ORD-8 established for Inventory.

**Not full cross-context atomicity, and why**: none of Sales' own use cases
(`StartSaleUseCase`/`AddSaleLineUseCase`/`RecordSalePaymentUseCase`/
`CheckoutSaleUseCase`/`ReverseSaleUseCase`) accept an `owns_transaction`
flag the way `PostInventoryMovementUseCase` does — each one always commits
its own `SalesUnitOfWork`. So the Sales-side call and this module's own
`OrdersDeliveryUnitOfWork` write are two separate, sequential transactions
on the same connection, never one SAVEPOINT — the exact same architectural
limit `CheckoutSaleUseCase`'s own docstring already documents for Caja
effects. Every use case here is therefore written retry-safe: the Sales
call happens FIRST (the harder-to-cleanly-undo I/O), and the cheap
Orders/Delivery-side projection update only happens after it has already
succeeded — a retry with the same `operation_id` re-enters an already-done
Sales step as a no-op (idempotent) and only completes whichever
Orders/Delivery-side write didn't make it the first time.

Neither `RecordSalePaymentUseCase` nor `Sale.reverse()` has its own
operation_id dedup (unlike `StartSaleUseCase`, guarded by `sales.
UNIQUE(operation_id)`), so `RecordOrderPaymentUseCase`/
`ReverseCustomerOrderUseCase` check `orders_delivery_outbox.
get_by_operation_id()` FIRST and short-circuit if this exact operation
already completed — closing the common retry case (client resent an
already-fulfilled request). The narrow window between "the Sales call
already committed" and "this module's own commit that would have made that
check succeed" is NOT covered by that guard and remains a known, accepted
gap — the same class of documented limit `CheckoutSaleUseCase` already
accepts for its own Caja side effect, not something this phase's scope
extends to closing with a full saga/compensation mechanism.

Cash-on-delivery money (`DriverCashCollection`/`DriverSettlement`, ORD-20/21)
is a SEPARATE mechanism: a driver's collected cash is reconciled against the
delivery job. When that order's Sale is paid in cash, the money is the same one
the driver carries, so it skips the drawer (`driver_collected`), and Finance
moves it between custodies without counting it twice (SDLC-ORD-001, see
`event_handlers/finance/driver_cash_handlers.py`).
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.orders_delivery.dto import CustomerOrderDTO
from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions
from backend.application.orders_delivery.result import OrderResult, fail_from_domain_error
from backend.application.orders_delivery.use_cases._base import _OrdersDeliveryBaseUseCase
from backend.application.sales.authorization import SalesAuthorizationPolicy
from backend.domain.orders_delivery.enums import (
    CollectionPaymentMethod,
    OrderStatus,
    PaymentStatus,
)
from backend.domain.orders_delivery.events import OrderEvents
from backend.domain.orders_delivery.exceptions import (
    OrderNotFoundError,
    OrderNotLinkedToSaleError,
    OrdersDeliveryDomainError,
    RefundNotAllowedError,
)
from backend.domain.orders_delivery.policies.order_lifecycle_policy import (
    OrderReservationRequiredPolicy,
)
from backend.domain.orders_delivery.policies.order_payment_policy import OrderPaymentPolicy
from backend.infrastructure.db.repositories.orders_delivery.unit_of_work import (
    OrdersDeliveryUnitOfWork,
)
from backend.infrastructure.integrations.orders_delivery_inventory_client import (
    OrdersDeliveryInventoryClient,
)
from backend.infrastructure.integrations.orders_delivery_sales_client import (
    OrdersDeliverySalesClient,
)


class ProjectOrderToSaleUseCase(_OrdersDeliveryBaseUseCase):
    def execute(
        self, connection, *, order_id: str, cashier_user_id: str, actor_user_id: str,
        operation_id: str, sales_authorization: SalesAuthorizationPolicy | None = None,
    ) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.ORDER_CONFIRM)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            order = uow.orders.get(order_id)
            if order is None:
                return fail_from_domain_error(
                    OrderNotFoundError(f"Pedido {order_id} no existe"), operation_id=operation_id)
            if order.sale_id:
                return OrderResult.ok(
                    "Pedido ya proyectado a venta", entity_id=order.id, operation_id=operation_id,
                    sale_id=order.sale_id, order=CustomerOrderDTO.from_entity(order))
            try:
                OrderReservationRequiredPolicy.ensure_confirmed(order.status)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)

        client = OrdersDeliverySalesClient(
            connection, branch_id=order.branch_id, sales_authorization=sales_authorization)
        try:
            sale_id = client.project_order_to_sale(
                order=order, cashier_user_id=cashier_user_id, actor_user_id=actor_user_id,
                operation_id=operation_id)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            order = uow.orders.get(order_id)
            try:
                order.link_sale(sale_id)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.orders.save(order)
            self._emit(
                uow, OrderEvents.SALE_PROJECTED, aggregate_type="CustomerOrder",
                entity_id=order.id, operation_id=operation_id, branch_id=order.branch_id,
                actor_user_id=actor_user_id, sale_id=sale_id)
        return OrderResult.ok(
            "Pedido proyectado a venta", entity_id=order.id, operation_id=operation_id,
            sale_id=sale_id, order=CustomerOrderDTO.from_entity(order))


class RecordOrderPaymentUseCase(_OrdersDeliveryBaseUseCase):
    def execute(
        self, connection, *, order_id: str, method: str, amount: Decimal, actor_user_id: str,
        operation_id: str, reference: str | None = None,
        sales_authorization: SalesAuthorizationPolicy | None = None,
    ) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.ORDER_CONFIRM)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            order = uow.orders.get(order_id)
            if order is None:
                return fail_from_domain_error(
                    OrderNotFoundError(f"Pedido {order_id} no existe"), operation_id=operation_id)
            if uow.outbox.get_by_operation_id(operation_id) is not None:
                # §58: `orders_delivery_outbox.operation_id` is globally
                # UNIQUE, so its presence means THIS exact operation already
                # completed — short-circuit instead of calling Sales' own
                # `RecordSalePaymentUseCase` again, which has no
                # operation_id dedup of its own and would double-charge the
                # sale on a naive retry.
                return OrderResult.ok(
                    "Pago ya registrado", entity_id=order.id, operation_id=operation_id,
                    payment_status=order.payment_status.value,
                    order=CustomerOrderDTO.from_entity(order))
            if not order.sale_id:
                return fail_from_domain_error(
                    OrderNotLinkedToSaleError(
                        f"El pedido {order_id} no ha sido proyectado a una venta"),
                    operation_id=operation_id)
            sale_id = order.sale_id
            driver_collected = method == "CASH" and self._driver_collects_cash(uow, order_id)

        client = OrdersDeliverySalesClient(
            connection, branch_id=order.branch_id, sales_authorization=sales_authorization)
        try:
            total_paid, sale_total = client.record_payment(
                sale_id=sale_id, method=method, amount=amount, actor_user_id=actor_user_id,
                operation_id=operation_id, reference=reference)
            target_status = OrderPaymentPolicy.resolve_from_amounts(
                total_paid=total_paid, order_total=sale_total)
            if target_status == PaymentStatus.PAID:
                client.complete_sale(
                    sale_id=sale_id, actor_user_id=actor_user_id, operation_id=operation_id,
                    driver_collected=driver_collected)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            order = uow.orders.get(order_id)
            try:
                order.apply_payment_status(target_status)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.orders.save(order)
            self._emit(
                uow, OrderEvents.PAYMENT_RECORDED, aggregate_type="CustomerOrder",
                entity_id=order.id, operation_id=operation_id, branch_id=order.branch_id,
                actor_user_id=actor_user_id, method=method, amount=str(amount),
                payment_status=target_status.value)
        return OrderResult.ok(
            "Pago registrado", entity_id=order.id, operation_id=operation_id,
            payment_status=target_status.value, order=CustomerOrderDTO.from_entity(order))

    @staticmethod
    def _driver_collects_cash(uow, order_id: str) -> bool:
        """¿Este pedido se cobra en efectivo a la puerta? Entonces el dinero lo
        trae el repartidor, y su cobro lo registra, no un cajón."""
        job = uow.delivery_jobs.get_by_order_id(order_id)
        collection = uow.cash_collections.get_by_job_id(job.id) if job else None
        return collection is not None and (
            collection.payment_method == CollectionPaymentMethod.CASH)


class ReverseCustomerOrderUseCase(_OrdersDeliveryBaseUseCase):
    """§43 "ReverseDeliveredOrder"/§22 refund: only a COMPLETED order with
    money actually collected can be reversed. Requires a distinct
    authorizer via `authorize_exception()` — the master prompt's own
    `authorize_exception()` docstring already names "reembolso" as one of
    its hot-authorization cases (built in ORD-1, first used for this
    purpose here)."""

    def execute(
        self, connection, *, order_id: str, reason: str, actor_user_id: str,
        authorizer_user_id: str, operation_id: str,
        sales_authorization: SalesAuthorizationPolicy | None = None,
    ) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.ORDER_REVERSE)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            order = uow.orders.get(order_id)
            if order is None:
                return fail_from_domain_error(
                    OrderNotFoundError(f"Pedido {order_id} no existe"), operation_id=operation_id)
            if uow.outbox.get_by_operation_id(operation_id) is not None:
                # Same idempotency reasoning as `RecordOrderPaymentUseCase`:
                # `Sale.reverse()` has no operation_id dedup either, and a
                # second real call would raise (it's only legal from
                # COMPLETED) — short-circuit on a confirmed-already-done
                # retry instead of letting that surface as a failure.
                return OrderResult.ok(
                    "Pedido ya reembolsado", entity_id=order.id, operation_id=operation_id,
                    order=CustomerOrderDTO.from_entity(order))
            if not order.sale_id:
                return fail_from_domain_error(
                    OrderNotLinkedToSaleError(
                        f"El pedido {order_id} no ha sido proyectado a una venta"),
                    operation_id=operation_id)
            if (order.status != OrderStatus.COMPLETED
                    or order.payment_status not in (PaymentStatus.PARTIALLY_PAID, PaymentStatus.PAID)):
                return fail_from_domain_error(
                    RefundNotAllowedError(
                        "Solo un pedido completado y pagado puede reversarse/reembolsarse"),
                    operation_id=operation_id)
            try:
                self._auth.authorize_exception(
                    authorizer_user_id=authorizer_user_id, requested_by=actor_user_id,
                    permission_code=OrdersDeliveryPermissions.ORDER_REVERSE,
                    operation_id=operation_id, reason=reason, order_id=order_id)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            sale_id = order.sale_id

        client = OrdersDeliverySalesClient(
            connection, branch_id=order.branch_id, sales_authorization=sales_authorization)
        inventory = OrdersDeliveryInventoryClient(connection, branch_id=order.branch_id)
        try:
            # La mercancía la sacó Pedidos, así que la devuelve Pedidos, dentro
            # de la transacción del reverso de la venta (SDLC-ORD-004).
            client.refund(
                sale_id=sale_id, reason=reason, actor_user_id=actor_user_id,
                authorizer_user_id=authorizer_user_id, operation_id=operation_id,
                restore_inventory=lambda: inventory.restore_order(
                    order, operation_id=operation_id, actor_user_id=actor_user_id,
                    reason_code="ORDER_REVERSAL"))
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            order = uow.orders.get(order_id)
            try:
                order.reverse()
                order.apply_payment_status(PaymentStatus.REFUNDED)
            except OrdersDeliveryDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.orders.save(order)
            self._emit(
                uow, OrderEvents.REFUNDED, aggregate_type="CustomerOrder", entity_id=order.id,
                operation_id=operation_id, branch_id=order.branch_id, actor_user_id=actor_user_id,
                authorized_by=authorizer_user_id, reason=reason)
        return OrderResult.ok(
            "Pedido reembolsado", entity_id=order.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(order))
