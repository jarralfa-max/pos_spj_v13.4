"""LOSS_FINANCE_RECOGNITION_REQUESTED — la merma valuada llega al mayor (§20).

Mermas valúa el expediente (costo bruto menos lo recuperado) y pide a Finanzas
reconocer la pérdida neta. Es costo, nunca dinero:

    Dr Merma (gasto)  /  Cr Inventario        por la pérdida neta

con la sucursal del expediente como dimensión. Además deja el hecho analítico
WASTE para la rentabilidad por sucursal (§33). Idempotente por evento y por
valuación (una valuación no se reconoce dos veces).
"""

from __future__ import annotations

from backend.application.event_handlers.finance.handler_base import FinanceEventHandler
from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.enums import JournalType, PostingPurpose
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.posting_reference import PostingReference

LOSS_FINANCE_RECOGNITION_REQUESTED = "LOSS_FINANCE_RECOGNITION_REQUESTED"


class LossRecognitionHandler(FinanceEventHandler):
    event_name = LOSS_FINANCE_RECOGNITION_REQUESTED

    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._engine = PostingEngine()

    def _handle(self, uow, payload: dict) -> None:
        valuation_id = str(payload.get("entity_id") or "").strip()
        loss_case_id = str(payload.get("loss_case_id") or "").strip()
        if not valuation_id or not loss_case_id:
            raise FinanceDomainError(f"{self.event_name}: faltan entity_id o loss_case_id")
        currency = self.currency(payload)
        amount = self.money(payload, "amount", currency)
        # El sobre de Mermas fecha el hecho en ``timestamp``.
        entry_date = self.event_date({**payload, "occurred_at": payload.get("occurred_at")
                                      or payload.get("timestamp")})
        if not amount.is_positive():
            return  # todo se recuperó: no hay pérdida que reconocer
        branch_id = payload.get("branch_id")
        profile = self.resolve_profile(uow, "INVENTORY", entry_date)
        entry = self._engine.post(
            uow, JournalType.INVENTORY, entry_date, f"Merma expediente {loss_case_id[-8:]}",
            PostingReference("losses", valuation_id, PostingPurpose.WASTE,
                             str(payload["operation_id"])),
            [
                LineSpec(profile.account_for("waste_expense_account_id"), debit=amount,
                         description="Pérdida neta por merma", branch_id=branch_id),
                LineSpec(profile.account_for("inventory_account_id"), credit=amount,
                         description="Salida de inventario por merma", branch_id=branch_id),
            ],
            currency_code=currency, branch_id=branch_id,
            created_by=payload.get("user_id"))
        uow.profitability.record(
            fact_type="WASTE", source_module="losses", source_document_id=valuation_id,
            line_reference=loss_case_id, journal_entry_id=entry.id,
            fact_date=entry_date.isoformat(), branch_id=branch_id, product_id=None,
            category_id=None, customer_id=None, channel=None, order_id=None, route_id=None,
            quantity="0", net_revenue="0.00", discount="0.00", cost_of_sales="0.00",
            direct_cost=amount.to_string(), currency_code=currency,
            operation_id=str(payload["operation_id"]))
