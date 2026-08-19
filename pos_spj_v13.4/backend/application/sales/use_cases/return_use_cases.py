"""ReturnSaleLineUseCase / ReverseSaleUseCase (POS-16/§42-44: Cancel [already
built — see `lifecycle_use_cases.py::CancelSaleUseCase`, pre-payment only],
Return, Reverse, Authorization, Tests).

**Authorization is NOT optional here**, unlike the discount use cases'
threshold-based `authorized: bool` flag. Research for this phase confirmed
a real, unaddressed gap: the legacy Devolución flow (`modulos/ventas.py::
_cancelar`) only re-checks a single flat permission
(`core.permissions.verificar_permiso`, `"ventas.cancelar"`) for the SAME
user who's already logged in — no PIN prompt, no second approver, nothing
resembling hot authorization anywhere in that path, even though
`SalesAuthorizationPolicy.authorize_exception` (real hot-auth machinery,
requiring a distinct authorizer) has existed since SALES-2 and is already
exercised for discounts. Every return/reversal here always requires a
distinct `authorizer_user_id` holding the same permission as the
requester — closing that gap for the new stack, not touching the legacy
path.

**Ordering matters for real atomicity** (same discipline as
`CheckoutSaleUseCase`, SALES-14, generalized one step further): the domain
mutation (`sale.return_line()`/`sale.reverse()`) is cheap and purely
in-memory, so it runs first. The inventory restoration
(`SalesInventoryClient.restore_for_return`, wrapping
`PostInventoryMovementUseCase` with `owns_transaction=False`) is real I/O
on the SAME physical connection but is NOT self-contained the way
`StockReservationService`'s own SAVEPOINT-wrapped methods are (SALES-9) —
a failure inside it does not clean up its own partial writes, because
`owns_transaction=False` deliberately defers that decision to whoever owns
the outer transaction. If it fails AFTER the domain mutation already
"succeeded" in memory, silently returning a failure result would let
`SalesUnitOfWork`'s own clean-exit-commits-by-default behavior commit
whatever partial inventory writes happened — so this module explicitly
calls `uow.rollback()` on that failure path instead of just returning,
rather than trusting the implicit no-op-commit safety every earlier phase's
simpler (pre-mutation-only) I/O calls could rely on.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.sales.dto import SaleDTO
from backend.application.sales.permissions import SalesPermissions
from backend.application.sales.result import SaleResult, fail_from_domain_error
from backend.application.sales.use_cases._base import _SalesBaseUseCase
from backend.domain.sales.events import SaleEvents
from backend.domain.sales.exceptions import SalesDomainError, SaleNotFoundError
from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork
from backend.infrastructure.integrations.sales_cash_effects_client import SalesCashEffectsClient
from backend.infrastructure.integrations.sales_inventory_client import SalesInventoryClient


class ReturnSaleLineUseCase(_SalesBaseUseCase):
    def execute(
        self, connection, *, sale_id: str, line_id: str, quantity: Decimal, reason: str,
        actor_user_id: str, authorizer_user_id: str, operation_id: str,
    ) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.RETURN)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with SalesUnitOfWork(connection) as uow:
            sale = uow.sales.get(sale_id)
            if sale is None:
                return fail_from_domain_error(
                    SaleNotFoundError(f"Venta {sale_id} no existe"), operation_id=operation_id)

            try:
                self._auth.authorize_exception(
                    authorizer_user_id=authorizer_user_id, requested_by=actor_user_id,
                    permission_code=SalesPermissions.RETURN, operation_id=operation_id,
                    reason=reason, amount=None, sale_id=sale_id)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)

            try:
                sale_return = sale.return_line(
                    line_id=line_id, quantity=quantity, reason=reason,
                    requested_by_user_id=actor_user_id,
                    authorized_by_user_id=authorizer_user_id)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)

            product_id = next(l.product_id for l in sale.lines if l.id == line_id)
            try:
                SalesInventoryClient(connection, branch_id=sale.branch_id).restore_for_return(
                    product_id=product_id, quantity=quantity, sale_id=sale.id,
                    operation_id=operation_id, actor_user_id=actor_user_id,
                    reason_code="SALE_RETURN", source_document_type="SALE_RETURN")
            except SalesDomainError as exc:
                uow.rollback()
                return fail_from_domain_error(exc, operation_id=operation_id)

            uow.sales.save(sale)
            self._emit(uow, SaleEvents.RETURNED, entity_id=sale.id, operation_id=operation_id,
                       branch_id=sale.branch_id, actor_user_id=actor_user_id,
                       line_id=line_id, quantity=str(quantity), amount=str(sale_return.amount),
                       authorized_by=authorizer_user_id, reason=reason,
                       fully_returned=sale.status.value == "RETURNED_FULLY")
        return SaleResult.ok(
            "Devolución registrada", entity_id=sale.id, operation_id=operation_id,
            sale=SaleDTO.from_entity(sale), return_id=sale_return.id,
            amount=sale_return.amount)


class ReverseSaleUseCase(_SalesBaseUseCase):
    def execute(
        self, connection, *, sale_id: str, reason: str, actor_user_id: str,
        authorizer_user_id: str, operation_id: str,
    ) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.REVERSE)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with SalesUnitOfWork(connection) as uow:
            sale = uow.sales.get(sale_id)
            if sale is None:
                return fail_from_domain_error(
                    SaleNotFoundError(f"Venta {sale_id} no existe"), operation_id=operation_id)

            try:
                self._auth.authorize_exception(
                    authorizer_user_id=authorizer_user_id, requested_by=actor_user_id,
                    permission_code=SalesPermissions.REVERSE, operation_id=operation_id,
                    reason=reason, amount=sale.totals.total, sale_id=sale_id)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)

            try:
                sale.reverse(reason)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)

            inv_client = SalesInventoryClient(connection, branch_id=sale.branch_id)
            for line in sale.lines:
                already_returned = sum(
                    (r.quantity for r in sale.returns if r.line_id == line.id), Decimal("0"))
                remaining = line.quantity.value - already_returned
                if remaining <= 0:
                    continue
                try:
                    inv_client.restore_for_return(
                        product_id=line.product_id, quantity=remaining, sale_id=sale.id,
                        operation_id=operation_id, actor_user_id=actor_user_id,
                        reason_code="SALE_REVERSAL", source_document_type="SALE_REVERSAL")
                except SalesDomainError as exc:
                    uow.rollback()
                    return fail_from_domain_error(exc, operation_id=operation_id)

            uow.sales.save(sale)
            self._emit(uow, SaleEvents.REVERSED, entity_id=sale.id, operation_id=operation_id,
                       branch_id=sale.branch_id, actor_user_id=actor_user_id, reason=reason,
                       authorized_by=authorizer_user_id)

        cash_effects_error: str | None = None
        if sale.payments:
            try:
                SalesCashEffectsClient().reverse_completed_sale(
                    connection, sale_id=sale.id, branch_id=sale.branch_id,
                    actor_user_id=actor_user_id, operation_id=operation_id, reason=reason)
            except Exception as exc:  # noqa: BLE001 - never un-reverse a sale over a ledger side effect
                cash_effects_error = str(exc)

        return SaleResult.ok(
            "Venta reversada", entity_id=sale.id, operation_id=operation_id,
            sale=SaleDTO.from_entity(sale), cash_effects_error=cash_effects_error)
