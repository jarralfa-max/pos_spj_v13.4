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

from decimal import Decimal

from backend.application.sales.dto import SaleDTO
from backend.application.sales.permissions import SalesPermissions
from backend.application.sales.result import SaleResult, fail_from_domain_error
from backend.application.sales.use_cases._base import _SalesBaseUseCase
from backend.domain.sales.events import SaleEvents
from backend.domain.sales.exceptions import LoyaltyRedemptionNotAvailableError, SalesDomainError, SaleNotFoundError
from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork
from backend.infrastructure.integrations.sales_loyalty_client import SalesLoyaltyClient


class RedeemLoyaltyPointsUseCase(_SalesBaseUseCase):
    def __init__(self, authorization=None, *, loyalty_authorization=None,
                 authorizer_authorization=None) -> None:
        super().__init__(authorization, authorizer_authorization=authorizer_authorization)
        #: Política con la que Ventas habla con Fidelidad (dueña del canje).
        #: Sin ella `SalesLoyaltyClient` falla cerrado — y así quedaba en el
        #: POS: el cliente se construía sin política y NINGÚN canje podía
        #: pasar (re-auditoría POS, 2026-10-01). Se inyecta desde la raíz de
        #: composición con el verificador real de la sesión.
        self._loyalty_auth = loyalty_authorization

    def execute(self, connection, *, sale_id: str, points: int, actor_user_id: str,
                operation_id: str, authorizer_user_id: str | None = None,
                reason: str | None = None) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.SALE_COMPLETE)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        autorizado = False
        if authorizer_user_id is not None:
            if not (reason or "").strip():
                return SaleResult.fail("Autorizar un beneficio sobre el margen requiere motivo",
                                       "MARGIN_PROTECTED", operation_id=operation_id)
            try:
                self._authorizer().authorize_exception(
                    authorizer_user_id=authorizer_user_id, requested_by=actor_user_id,
                    permission_code=SalesPermissions.DISCOUNT_OVERRIDE,
                    operation_id=operation_id, reason=reason, amount=Decimal("0"),
                    sale_id=sale_id)
                autorizado = True
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)

        with SalesUnitOfWork(connection) as uow:
            sale, denied = self._load_sale(uow, sale_id, actor_user_id, operation_id)
            if denied is not None:
                return denied
            if sale.customer_id is None:
                return fail_from_domain_error(
                    LoyaltyRedemptionNotAvailableError(
                        "El canje de fidelidad requiere un cliente asignado"),
                    operation_id=operation_id)

            cliente_puntos = SalesLoyaltyClient(
                connection, actor_branch_id=sale.branch_id, authorization=self._loyalty_auth)
            # Sin puntos no hay nada que autorizar: decirlo ANTES que el margen,
            # o el cajero pide una autorización que no sirve para nada.
            if not cliente_puntos.has_redeemable_points(customer_id=sale.customer_id,
                                                         sale_id=sale.id):
                return fail_from_domain_error(
                    LoyaltyRedemptionNotAvailableError("El cliente no tiene puntos disponibles"),
                    operation_id=operation_id)

            # FID-03: el descuento por puntos cabe en el margen de la venta.
            from backend.application.sales.queries.benefit_budget_query import (
                SaleBenefitBudgetQuery,
            )
            presupuesto = SaleBenefitBudgetQuery(connection).for_sale(sale)
            if not autorizado and (presupuesto.lines_without_cost
                                   or presupuesto.available <= 0):
                return SaleResult.fail(
                    presupuesto.explain() + " Pide autorización a quien pueda aprobarla.",
                    "MARGIN_PROTECTED", operation_id=operation_id)
            redemption = cliente_puntos.redeem(
                customer_id=sale.customer_id, sale_id=sale.id,
                subtotal=sale.totals.gross_subtotal, points=points,
                actor_user_id=actor_user_id,
                max_discount=None if autorizado else presupuesto.available)
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
