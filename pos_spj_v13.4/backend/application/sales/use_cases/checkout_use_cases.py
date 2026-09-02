"""CheckoutSaleUseCase — POS-14's "Atomic operation" (Cash, Card, Transfer,
Mixed, Credit, Mercado Pago already recorded via SALES-13's
`RecordSalePaymentUseCase`; Loyalty already settled, if requested, via
`RedeemLoyaltyPointsUseCase`; this is the single all-or-nothing finalize
step a "Cobrar" button triggers once).

**Atomicity, and why the ordering here is not arbitrary**: everything that
must succeed together — confirming the inventory hold and completing the
sale — happens inside ONE `SalesUnitOfWork`. To make that a genuine
guarantee rather than a hopeful one, the two domain checks that can still
fail (`SaleLifecyclePolicy.ensure_transition`, `SalePaymentPolicy.
ensure_fully_paid`) run FIRST, before any I/O mutation — so if checkout
can't legally complete, nothing is touched and the transaction commits an
unchanged no-op. Only once completion is already guaranteed to succeed does
the (harder to cleanly undo) inventory-reservation confirmation run, then
`Sale.complete()` itself (a cheap, guaranteed-to-pass re-check).

**Outbox**: `PAYMENT_CONFIRMED`/`COMPLETED` are enqueued to `sales_outbox`
inside that SAME transaction — if anything above fails, no event survives.

**Cash effects, and the one part of "atomic" this use case cannot deliver
honestly**: `SalesCashEffectsClient` wraps Caja's real
`CashSalesIntegrationService.record_completed_sale` — but `Cash Register`'s
own `CashRegisterUnitOfWork` has no `owns_transaction=False` mode (unlike
Sales'/Inventory's), so it cannot be composed into the same SAVEPOINT
without prematurely committing it. This step therefore runs AFTER the
sale's own transaction has already committed, as a best-effort, logged,
idempotent side effect — a genuine architectural limit found by this
phase's own research, not an oversight papered over. A failure here never
un-completes the sale (the cashier already collected real payment by this
point); it is recorded for reconciliation instead.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from backend.application.sales.dto import SaleDTO
from backend.application.sales.permissions import SalesPermissions
from backend.application.sales.result import SaleResult, fail_from_domain_error
from backend.application.sales.use_cases._base import _SalesBaseUseCase
from backend.domain.sales.enums import SaleStatus
from backend.domain.sales.events import SaleEvents
from backend.domain.sales.exceptions import SalesDomainError, SaleNotFoundError
from backend.domain.sales.policies.lifecycle_policies import SaleLifecyclePolicy
from backend.domain.sales.policies.payment_policy import SalePaymentPolicy
from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork
from backend.infrastructure.integrations.sales_cash_effects_client import SalesCashEffectsClient
from backend.infrastructure.integrations.sales_inventory_client import SalesInventoryClient
from backend.infrastructure.integrations.sales_sweepstakes_client import SalesSweepstakesClient

logger = logging.getLogger("spj.sales.checkout")


class CheckoutSaleUseCase(_SalesBaseUseCase):
    def execute(self, connection, *, sale_id: str, actor_user_id: str,
                operation_id: str) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.SALE_COMPLETE)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with SalesUnitOfWork(connection) as uow:
            sale = uow.sales.get(sale_id)
            if sale is None:
                return fail_from_domain_error(
                    SaleNotFoundError(f"Venta {sale_id} no existe"), operation_id=operation_id)

            try:
                SaleLifecyclePolicy.ensure_transition(
                    current=sale.status, target=SaleStatus.COMPLETED)
                SalePaymentPolicy.ensure_fully_paid(
                    total_paid=sale.total_paid, sale_total=sale.totals.total)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)

            if sale.inventory_reservation_id:
                inv_client = SalesInventoryClient(connection, branch_id=sale.branch_id)
                try:
                    inv_client.confirm(sale.inventory_reservation_id, sale_id=sale.id,
                                       folio=sale.sale_number or sale.id)
                except SalesDomainError as exc:
                    return fail_from_domain_error(exc, operation_id=operation_id)

            sale.complete()
            uow.sales.save(sale)
            self._emit(uow, SaleEvents.PAYMENT_CONFIRMED, entity_id=sale.id,
                       operation_id=operation_id, branch_id=sale.branch_id,
                       actor_user_id=actor_user_id)
            self._emit(uow, SaleEvents.COMPLETED, entity_id=sale.id, operation_id=operation_id,
                       branch_id=sale.branch_id, actor_user_id=actor_user_id,
                       total=str(sale.totals.total))

        cash_effects_error: str | None = None
        if sale.payments:
            change = max(Decimal("0"), sale.total_paid - sale.totals.total)
            try:
                SalesCashEffectsClient().record_completed_sale(
                    connection, sale_id=sale.id, branch_id=sale.branch_id,
                    cashier_user_id=sale.cashier_user_id, operation_id=operation_id,
                    payments=sale.payments, change=change)
            except Exception as exc:  # noqa: BLE001 - never un-complete a sale over a ledger side effect
                cash_effects_error = str(exc)
                logger.warning("Efecto de caja no registrado para venta %s: %s", sale.id, exc)

        raffle_issue_error: str | None = None
        try:
            SalesSweepstakesClient(connection).issue_tickets_for_sale(sale=SaleDTO.from_entity(sale))
        except Exception as exc:  # noqa: BLE001 - never un-complete a sale over raffle issuance
            raffle_issue_error = str(exc)
            logger.warning("Boletos de rifa no emitidos para venta %s: %s", sale.id, exc)

        return SaleResult.ok(
            "Venta finalizada", entity_id=sale.id, operation_id=operation_id,
            sale=SaleDTO.from_entity(sale), cash_effects_error=cash_effects_error,
            raffle_issue_error=raffle_issue_error)
