"""RedeemLoyaltyPointsUseCase (POS-14/§38-41: "Loyalty").

`SaleBenefitEvaluationService` (SALES-11) can only PREVIEW a redemption —
its own docstring is explicit that Loyalty evaluation degrades to a
warning, never commits anything. This use case is the real counterpart:
it actually deducts points (via `SalesLoyaltyClient.redeem()`, which itself
re-previews to get the authoritative clamped point count before
committing) and reduces the Sale's own `totals.loyalty_total` through
`Sale.apply_loyalty_redemption()` — the field SALES-3 reserved in
`SaleTotals` from the start but nothing populated until now.

Deliberately reuses `SalesPermissions.SALE_COMPLETE` rather than minting a
new permission code: redeeming points is an action taken in service of
completing a sale, not a distinct capability a role would be granted
independently of being allowed to close a sale at all — same reasoning
`AssignCustomerToSaleUseCase` (SALES-6) already applied for its own
compound action.
"""

from __future__ import annotations

from backend.application.sales.dto import SaleDTO
from backend.application.sales.permissions import SalesPermissions
from backend.application.sales.result import SaleResult, fail_from_domain_error
from backend.application.sales.use_cases._base import _SalesBaseUseCase
from backend.domain.sales.events import SaleEvents
from backend.domain.sales.exceptions import LoyaltyRedemptionNotAvailableError, SalesDomainError, SaleNotFoundError
from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork
from backend.infrastructure.integrations.sales_loyalty_client import SalesLoyaltyClient


class RedeemLoyaltyPointsUseCase(_SalesBaseUseCase):
    def execute(self, connection, *, sale_id: str, points: int, actor_user_id: str,
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
            if sale.customer_id is None:
                return fail_from_domain_error(
                    LoyaltyRedemptionNotAvailableError(
                        "El canje de fidelidad requiere un cliente asignado"),
                    operation_id=operation_id)

            redemption = SalesLoyaltyClient(connection).redeem(
                customer_id=sale.customer_id, sale_id=sale.id,
                subtotal=sale.totals.gross_subtotal, points=points,
                actor_user_id=actor_user_id)
            if not redemption["approved"]:
                return fail_from_domain_error(
                    LoyaltyRedemptionNotAvailableError(redemption["reason"]),
                    operation_id=operation_id)

            try:
                sale.apply_loyalty_redemption(redemption["discount_amount"])
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)

            uow.sales.save(sale)
            self._emit(uow, SaleEvents.LOYALTY_REDEEMED, entity_id=sale.id,
                       operation_id=operation_id, branch_id=sale.branch_id,
                       actor_user_id=actor_user_id,
                       points_redeemed=redemption["points_redeemed"],
                       discount_amount=str(redemption["discount_amount"]))
        return SaleResult.ok("Fidelidad canjeada", entity_id=sale.id, operation_id=operation_id,
                             sale=SaleDTO.from_entity(sale),
                             points_redeemed=redemption["points_redeemed"])
