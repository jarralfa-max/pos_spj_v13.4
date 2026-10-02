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


class _ReturnBaseUseCase(_SalesBaseUseCase):
    """El AUTORIZADOR de una devolución o un reverso es OTRO usuario. Con la
    política de sesión (que sólo responde por el cajero en turno) se le negaba
    siempre: en el POS ninguna devolución podía autorizarse (re-auditoría POS,
    2026-10-01). Mismo estándar que el descuento y el cobro sin existencia: la
    raíz de composición inyecta `AuthorizerPermissionChecker`."""

    def __init__(self, authorization=None, inventory_authorization=None,
                 customer_authorization=None, *, authorizer_authorization=None,
                 cash_refund_service=None) -> None:
        super().__init__(authorization, inventory_authorization, customer_authorization)
        self._authorizer_auth = authorizer_authorization or self._auth
        #: `CashRefundIntegrationService` de Caja (con su política). Sin él, la
        #: devolución no registra la salida de efectivo (pruebas, Delivery).
        self._cash_refunds = cash_refund_service


class ReturnSaleLineUseCase(_ReturnBaseUseCase):
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
                self._authorizer_auth.authorize_exception(
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

            # Por dónde se reembolsa (método original, efectivo primero).
            refunds = sale.refund_plan(sale_return.amount)
            if self._cash_refunds is not None and any(m == "CASH" for m, _ in refunds):
                # El efectivo sale del cajón de quien devuelve: sin su turno
                # abierto, Caja lo rechazaría DESPUÉS de haber devuelto la
                # mercancía. Se valida antes de tocar nada.
                problema = self._open_shift_problem(connection, sale.branch_id, actor_user_id)
                if problema:
                    return SaleResult.fail(problema, "NO_OPEN_CASH_SHIFT",
                                           operation_id=operation_id)

            line = next(l for l in sale.lines if l.id == line_id)
            try:
                cogs = self._inventory_client(
                    connection, branch_id=sale.branch_id,
                    actor_user_id=actor_user_id).restore_for_return(
                    product_id=line.product_id, quantity=quantity, sale_id=sale.id,
                    operation_id=operation_id, actor_user_id=actor_user_id,
                    reason_code="SALE_RETURN", source_document_type="SALE_RETURN")
            except SalesDomainError as exc:
                uow.rollback()
                return fail_from_domain_error(exc, operation_id=operation_id)

            tax_amount = (line.tax_total * quantity / line.quantity.value).quantize(Decimal("0.01"))
            # Bruto de lo devuelto, antes del descuento a nivel venta: Finanzas
            # revierte el descuento por la diferencia con el importe neto.
            gross_amount = max((line.line_total * quantity / line.quantity.value).quantize(
                Decimal("0.01")), sale_return.amount)
            uow.sales.save(sale)
            self._emit(uow, SaleEvents.RETURNED, entity_id=sale.id, operation_id=operation_id,
                       branch_id=sale.branch_id, actor_user_id=actor_user_id,
                       line_id=line_id, product_id=line.product_id,
                       quantity=str(quantity), amount=str(sale_return.amount),
                       gross_amount=str(gross_amount), tax_amount=str(tax_amount),
                       cogs_amount=str(cogs or Decimal("0")),
                       refunds=[{"method": m, "amount": str(a)} for m, a in refunds],
                       return_id=sale_return.id, folio=sale.sale_number or sale.id[-8:],
                       sale_total=str(sale.totals.total),
                       refunded_total=str(sum((r.amount for r in sale.returns), Decimal("0"))),
                       customer_id=sale.customer_id, currency_code=sale.currency_code,
                       authorized_by=authorizer_user_id, reason=reason,
                       fully_returned=sale.status.value == "RETURNED_FULLY")

        cash_effects_error: str | None = None
        if self._cash_refunds is not None:
            try:
                SalesCashEffectsClient().refund_returned_line(
                    connection, self._cash_refunds, refund_id=sale_return.id, sale_id=sale.id,
                    branch_id=sale.branch_id, actor_user_id=actor_user_id,
                    authorized_by=authorizer_user_id, operation_id=operation_id,
                    payments=sale.payments, change=sale.change_given, refunds=refunds,
                    reason=reason)
            except Exception as exc:  # noqa: BLE001 - la mercancía ya volvió; se informa
                cash_effects_error = str(exc)
        return SaleResult.ok(
            "Devolución registrada", entity_id=sale.id, operation_id=operation_id,
            sale=SaleDTO.from_entity(sale), return_id=sale_return.id,
            amount=sale_return.amount, refunds=refunds, cash_effects_error=cash_effects_error)

    @staticmethod
    def _open_shift_problem(connection, branch_id: str, actor_user_id: str) -> str | None:
        import sqlite3

        from backend.domain.cash_register.exceptions import CashRegisterError
        try:
            SalesCashEffectsClient().require_open_shift(
                connection, branch_id=branch_id, cashier_user_id=actor_user_id)
        except (CashRegisterError, sqlite3.OperationalError):
            return ("Para devolver efectivo necesitas tu turno de caja abierto: el reembolso "
                    "sale de tu cajón.")
        return None


class ReverseSaleUseCase(_ReturnBaseUseCase):
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
                self._authorizer_auth.authorize_exception(
                    authorizer_user_id=authorizer_user_id, requested_by=actor_user_id,
                    permission_code=SalesPermissions.REVERSE, operation_id=operation_id,
                    reason=reason, amount=sale.totals.total, sale_id=sale_id)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)

            try:
                sale.reverse(reason)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)

            inv_client = self._inventory_client(
                connection, branch_id=sale.branch_id, actor_user_id=actor_user_id)
            for line in sale.lines:
                already_returned = sum(
                    (r.quantity for r in sale.returns if r.line_id == line.id), Decimal("0"))
                remaining = line.quantity.value - already_returned
                if remaining <= 0:
                    continue
                try:
                    inv_client.restore_for_return(
                        product_id=line.product_id, quantity=remaining, sale_id=sale.id,
                        # Una identidad por LÍNEA: el movimiento es idempotente
                        # por operation_id, y con la del reverso entero sólo la
                        # primera línea regresaba al inventario.
                        operation_id=f"{operation_id}:{line.id}",
                        actor_user_id=actor_user_id,
                        reason_code="SALE_REVERSAL", source_document_type="SALE_REVERSAL")
                except SalesDomainError as exc:
                    uow.rollback()
                    return fail_from_domain_error(exc, operation_id=operation_id)

            uow.sales.save(sale)
            self._emit(uow, SaleEvents.REVERSED, entity_id=sale.id, operation_id=operation_id,
                       branch_id=sale.branch_id, actor_user_id=actor_user_id, reason=reason,
                       authorized_by=authorizer_user_id, customer_id=sale.customer_id,
                       sale_total=str(sale.totals.total),
                       folio=sale.sale_number or sale.id[-8:])

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
