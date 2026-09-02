"""OrdersDeliverySalesClient — Pedidos/Delivery's own integration point onto
Sales (master prompt §22: a CustomerOrder projects into a commercial `Sale`;
Orders/Delivery never writes `sales`/`sale_lines` tables directly, exactly
the same "Inventario ejecuta, Pedidos no escribe" discipline `OrdersDelivery
InventoryClient` (ORD-8) already established for Inventory). Wraps the REAL
Sales use cases (`StartSaleUseCase`/`AddSaleLineUseCase`/
`RecordSalePaymentUseCase`/`CheckoutSaleUseCase`/`ReverseSaleUseCase`) —
`CheckoutSaleUseCase` rather than the plainer `CompleteSaleUseCase` because
it already carries the real Caja/loyalty side effects (`SalesCashEffectsClient`),
which is exactly the "Caja" half of this phase's scope; this client does not
reimplement cash-drawer or credit logic, both already live inside the Sales
use cases it calls.

**Authorization is intentionally NOT defaulted to permissive here** — unlike
`OrdersDeliveryInventoryClient`, which silently relies on Inventory's own
use cases defaulting their bare constructor to `permissive_for_tests()` (a
real, still-open gap from ORD-8, not fixed by this phase). Sales' own
`_SalesBaseUseCase` deliberately FAILS CLOSED when no `SalesAuthorizationPolicy`
checker is supplied (`SalesConfigurationError`, its own docstring: "an
unconfigured authorization gate must never allow"). Respecting that
hardening rather than routing around it, this client requires the caller to
supply a real `SalesAuthorizationPolicy` for production wiring; tests supply
`SalesAuthorizationPolicy.permissive_for_tests()` explicitly, same as every
other test in this codebase already does for Sales use cases.

Per-line/per-step operation ids are always freshly minted via `new_uuid()`,
never derived by suffixing the caller's `operation_id` — `sale_event_payload()`
validates `operation_id` as a real UUIDv7 exactly like `orders_delivery`'s own
event payload builders do (confirmed by reading `backend/domain/sales/
events.py`), so a suffixed string (ORD-8's per-line pattern, safe only
because Inventory's own event payload builder does NOT validate UUIDv7
format) would raise here — the exact class of bug ORD-21 found and fixed.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.sales.authorization import SalesAuthorizationPolicy
from backend.application.sales.use_cases.cart_use_cases import (
    AddSaleLineUseCase,
    StartSaleUseCase,
)
from backend.application.sales.use_cases.checkout_use_cases import CheckoutSaleUseCase
from backend.application.sales.use_cases.lifecycle_use_cases import BeginSaleCheckoutUseCase
from backend.application.sales.use_cases.payment_use_cases import RecordSalePaymentUseCase
from backend.application.sales.use_cases.return_use_cases import ReverseSaleUseCase
from backend.domain.orders_delivery.exceptions import SaleProjectionFailedError
from backend.shared.ids import new_uuid


class OrdersDeliverySalesClient:
    def __init__(self, connection, *, branch_id: str,
                 sales_authorization: SalesAuthorizationPolicy | None = None) -> None:
        self._connection = connection
        self._branch_id = branch_id
        self._auth = sales_authorization

    def project_order_to_sale(
        self, *, order, cashier_user_id: str, actor_user_id: str, operation_id: str,
    ) -> str:
        """§22: starts a Sale with one line per `CustomerOrderLine`, billed
        against `CustomerOrderLine.billable_quantity()` (final if the line
        has been prepared/adjusted, requested otherwise — same priority
        `final_subtotal` already uses). `operation_id` is the SAME one the
        caller uses for the whole projection — `StartSaleUseCase` is
        idempotent on it (`sales.UNIQUE(operation_id)`), so a retried
        projection call returns the already-started Sale instead of erroring
        or duplicating it.

        **`AddSaleLineUseCase` itself has no such idempotency guard** — unlike
        `StartSaleUseCase`, calling it twice for the same line always adds a
        second one. A retry that lands here after the Sale was already
        started (but the caller crashed before this method returned) must
        not re-add lines to it, so this method checks the started Sale's own
        line count first and only adds lines when it is genuinely empty.

        Once lines are in place the Sale is moved ACTIVE -> CHECKOUT_PENDING
        (`BeginSaleCheckoutUseCase`) so `record_payment()` can legally record
        against it (`SalePaymentPolicy.ensure_can_record_payment` only
        allows CHECKOUT_PENDING/PAYMENT_PENDING, never ACTIVE) — this too is
        skipped on a retry that finds the Sale already past ACTIVE."""
        start_result = StartSaleUseCase(self._auth).execute(
            self._connection, branch_id=self._branch_id, cashier_user_id=cashier_user_id,
            operation_id=operation_id, actor_user_id=actor_user_id,
            channel=order.channel.value, currency_code=order.currency_code)
        if not start_result.success:
            raise SaleProjectionFailedError(start_result.message)
        sale_id = start_result.entity_id
        sale = start_result.data["sale"]

        if not sale.lines:
            for line in order.lines:
                line_result = AddSaleLineUseCase(self._auth).execute(
                    self._connection, sale_id=sale_id, product_id=line.product_id,
                    quantity=line.billable_quantity(), unit_price=line.unit_price_snapshot,
                    actor_user_id=actor_user_id, operation_id=new_uuid(),
                    quantity_unit=line.billable_unit(), product_snapshot=line.product_snapshot)
                if not line_result.success:
                    raise SaleProjectionFailedError(line_result.message)
                sale = line_result.data["sale"]

        if sale.status == "ACTIVE":
            checkout_result = BeginSaleCheckoutUseCase(self._auth).execute(
                self._connection, sale_id=sale_id, actor_user_id=actor_user_id,
                operation_id=new_uuid())
            if not checkout_result.success:
                raise SaleProjectionFailedError(checkout_result.message)
        return sale_id

    def record_payment(
        self, *, sale_id: str, method: str, amount: Decimal, actor_user_id: str,
        operation_id: str, reference: str | None = None,
    ) -> tuple[Decimal, Decimal]:
        """Returns `(total_paid, sale_total)` so the caller can resolve the
        order's own `PaymentStatus` via `OrderPaymentPolicy.
        resolve_from_amounts()` without this client reaching back into Sales
        a second time."""
        result = RecordSalePaymentUseCase(self._auth).execute(
            self._connection, sale_id=sale_id, method=method, amount=amount,
            actor_user_id=actor_user_id, operation_id=operation_id, reference=reference)
        if not result.success:
            raise SaleProjectionFailedError(result.message)
        sale = result.data["sale"]
        return sale.total_paid, sale.total

    def complete_sale(self, *, sale_id: str, actor_user_id: str, operation_id: str) -> None:
        """Finalizes the Sale (`CheckoutSaleUseCase`) — confirms any
        inventory hold, marks it COMPLETED, and runs the real Caja/loyalty
        side effects. A Caja-effect failure is logged by `CheckoutSaleUseCase`
        itself and never un-completes the sale; it is not this client's job
        to second-guess that."""
        result = CheckoutSaleUseCase(self._auth).execute(
            self._connection, sale_id=sale_id, actor_user_id=actor_user_id,
            operation_id=operation_id)
        if not result.success:
            raise SaleProjectionFailedError(result.message)

    def refund(
        self, *, sale_id: str, reason: str, actor_user_id: str, authorizer_user_id: str,
        operation_id: str,
    ) -> None:
        """A CustomerOrder has no per-line return tracking of its own, so a
        refund always reverses the WHOLE linked Sale (`ReverseSaleUseCase`,
        which itself restores inventory and reverses Caja effects) — never a
        partial `ReturnSaleLineUseCase`. `authorizer_user_id` flows straight
        into Sales' own hot-authorization (`SalesAuthorizationPolicy.
        authorize_exception`, requiring a distinct approver) — this client
        does not additionally gate on an Orders/Delivery-side authorizer."""
        result = ReverseSaleUseCase(self._auth).execute(
            self._connection, sale_id=sale_id, reason=reason, actor_user_id=actor_user_id,
            authorizer_user_id=authorizer_user_id, operation_id=operation_id)
        if not result.success:
            raise SaleProjectionFailedError(result.message)
