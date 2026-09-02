"""SalesSweepstakesClient — Sales' integration point onto the real
Sweepstakes/raffle capability (SET-15 cutover). Mirrors
`sales_loyalty_client.py`'s shape: Sales' own boundary onto
`core/services/loyalty_service.py::LoyaltyService` (the real owner of
LEGACY raffle business rules), never re-derived here.

**Zero identity bridging needed** — unlike `SalesLoyaltyClient`, which
must bridge Customer Master's UUID to a legacy `clientes.id` row.
`LoyaltyService`'s raffle methods treat `venta_id`/`cliente_id`/
`sucursal_id` as opaque strings throughout (confirmed by reading
`issue_raffle_tickets_for_sale`'s body: it never joins against a legacy
table by `venta_id`), so a real UUIDv7 `sale.id`/`sale.branch_id` works
directly. `sucursal_id` is always passed explicitly — `LoyaltyService`'s
own `sucursal_id: int = 1` constructor default is never relied on.

Decimal -> float conversion happens here and only here (same boundary
discipline as `SalesLoyaltyClient`/`SalesInventoryClient`) —
`LoyaltyService`'s raffle methods are legacy-typed and never touch
Sales' own Decimal totals directly.

**LOY-24**: also grants entries in the NEW `backend.domain.sweepstakes`
bounded context (LOY-15) for any ACTIVE `SweepstakesCampaign` with a
`PURCHASE_AMOUNT` rule — running alongside the legacy raffle call above,
not replacing it, until LOY-27 can retire the legacy subsystem entirely
(CLAUDE.md Prioridad 0: no legacy deletion without a proven replacement).
`GrantSweepstakesEntryFromSaleUseCase` is itself best-effort/no-op-safe
(never raises for "doesn't qualify"), and this method's own caller
(`CheckoutSaleUseCase`) already wraps this whole call in a
never-un-complete-the-sale `try/except` — no additional safety net needed
here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.application.sales.dto import SaleDTO


class SalesSweepstakesClient:
    def __init__(self, connection) -> None:
        self._connection = connection

    def issue_tickets_for_sale(self, *, sale: "SaleDTO") -> None:
        from core.services.loyalty_service import LoyaltyService

        service = LoyaltyService(self._connection, sucursal_id=sale.branch_id)
        service.process_raffles_for_sale(
            venta_id=sale.id,
            cliente_id=sale.customer_id or "",
            folio=sale.sale_number or sale.id,
            total=float(sale.total),
            sucursal_id=sale.branch_id,
            payment_method=self._forma_pago(sale),
            items=[{"product_id": line.product_id} for line in sale.lines],
            discount=float(sale.discount_total),
        )
        self._grant_new_sweepstakes_entries(sale)

    def _grant_new_sweepstakes_entries(self, sale: "SaleDTO") -> None:
        if not sale.customer_id:
            return
        from backend.application.sweepstakes.use_cases.entry_use_cases import (
            GrantSweepstakesEntryFromSaleUseCase,
        )
        from backend.infrastructure.db.repositories.sweepstakes.unit_of_work import (
            SweepstakesUnitOfWork,
        )
        from backend.shared.ids import new_uuid

        with SweepstakesUnitOfWork(self._connection) as uow:
            campaigns = uow.campaigns.list_active()
        for campaign in campaigns:
            GrantSweepstakesEntryFromSaleUseCase().execute(
                self._connection, campaign_id=campaign.id, customer_id=sale.customer_id,
                source_sale_id=sale.id, sale_amount=sale.total, actor_branch_id=sale.branch_id,
                operation_id=new_uuid())

    def get_printable_tickets_for_sale(self, *, sale_id: str) -> list[dict]:
        from core.services.loyalty_service import LoyaltyService

        service = LoyaltyService(self._connection)
        return service.get_printable_tickets_for_sale(sale_id)

    @staticmethod
    def _forma_pago(sale: "SaleDTO") -> str:
        """Same derivation `SalesReceiptClient.build_receipt_data_from_sale`
        already established for the receipt — kept consistent rather than
        re-invented, since raffle payment-method rules should see the same
        label the printed receipt shows."""
        if sale.is_mixed_payment:
            return "Mixto"
        if len(sale.payments) == 1:
            return sale.payments[0].method
        return ""
