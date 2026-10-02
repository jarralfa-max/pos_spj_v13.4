"""SALE_RETURNED handler — la devolución PARCIAL de una venta, en espejo de
`SaleCompletedHandler` (decisión del usuario 2026-10-02).

Hasta ahora una devolución parcial reponía inventario y no tocaba nada más: el
ingreso, el IVA y el costo de venta seguían como si la mercancía no hubiera
vuelto, y el dinero devuelto no estaba en ningún asiento.

Asiento de la devolución (uno por devolución, idempotente por `return_id`):

    Dr ingreso        (bruto proporcional - IVA)
    Dr IVA trasladado (IVA proporcional)
      Cr descuento    (la parte del descuento a nivel venta que se devuelve)
      Cr efectivo / banco / tarjeta-procesador / CxC   (por método de reembolso)

y, si salió con costo, la reversa del costo de venta:

    Dr inventario / Cr costo de venta

Lo reembolsado A CRÉDITO no mueve dinero: emite una NOTA DE CRÉDITO que baja la
CxC de la venta. No puede exceder lo que el cliente aún debe (un excedente
sería un saldo a favor, que es otro instrumento).
"""

from __future__ import annotations

from backend.application.event_handlers.finance.handler_base import FinanceEventHandler
from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.entities.financial_document import FinancialDocument
from backend.domain.finance.enums import (
    FinancialDocumentType,
    JournalType,
    PostingPurpose,
    SettlementType,
)
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.shared.ids import new_uuid

_ACCOUNT_BY_SETTLEMENT = {
    SettlementType.CASH: ("cash_account_id", "Reembolso en efectivo"),
    SettlementType.BANK_TRANSFER: ("bank_account_id", "Reembolso por transferencia"),
    SettlementType.CARD: ("clearing_account_id", "Reembolso a tarjeta"),
    SettlementType.PAYMENT_PROCESSOR: ("clearing_account_id", "Reembolso por procesador"),
    SettlementType.ON_CREDIT: ("receivable_account_id", "Nota de crédito"),
}


class SaleReturnedHandler(FinanceEventHandler):
    event_name = "SALE_RETURNED"

    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._engine = PostingEngine()

    def _handle(self, uow, payload: dict) -> None:
        currency = self.currency(payload)
        sale_id = str(payload.get("sale_id") or "")
        return_id = str(payload.get("return_id") or "")
        if not sale_id or not return_id:
            raise FinanceDomainError("SALE_RETURNED sin sale_id/return_id")
        entry_date = self.event_date(payload)
        branch_id = payload.get("branch_id")
        folio = str(payload.get("folio") or sale_id[:8])

        amount = self.money(payload, "amount", currency)
        gross = self.money(payload, "gross_amount", currency, required=False)
        if gross.amount < amount.amount:
            gross = amount
        tax = self.money(payload, "tax_amount", currency, required=False)
        discount = gross.subtract(amount)

        refunds = payload.get("refunds") or []
        refunded = Money.zero(currency)
        for refund in refunds:
            refunded = refunded.add(Money.from_string(str(refund["amount"]), currency))
        if refunded.amount != amount.amount:
            raise FinanceDomainError(
                f"Devolución {folio}: el reembolso {refunded.to_string()} no coincide con "
                f"el importe devuelto {amount.to_string()}")

        profile = self.resolve_profile(uow, "SALE", entry_date)
        lines = [LineSpec(profile.account_for("revenue_account_id"), debit=gross.subtract(tax),
                          description=f"Devolución venta {folio}")]
        if tax.is_positive():
            lines.append(LineSpec(profile.account_for("tax_account_id"), debit=tax,
                                  description=f"IVA devolución {folio}"))
        if discount.is_positive():
            lines.append(LineSpec(profile.account_for("discount_account_id"), credit=discount,
                                  description=f"Descuento devuelto {folio}"))
        credito = Money.zero(currency)
        for refund in refunds:
            tipo = SettlementType(str(refund["type"]))
            importe = Money.from_string(str(refund["amount"]), currency)
            if importe.is_zero():
                continue
            if tipo not in _ACCOUNT_BY_SETTLEMENT:
                raise FinanceDomainError(f"Reembolso por {tipo.value} no soportado")
            role, texto = _ACCOUNT_BY_SETTLEMENT[tipo]
            lines.append(LineSpec(profile.account_for(role), credit=importe,
                                  description=f"{texto} {folio}"))
            if tipo is SettlementType.ON_CREDIT:
                credito = credito.add(importe)

        entry = self._engine.post(
            uow, JournalType.SALES, entry_date, f"Devolución {folio}",
            PostingReference("sales", return_id, PostingPurpose.SALE_RETURN,
                             str(payload["operation_id"])),
            lines, currency_code=currency, branch_id=branch_id)

        if credito.is_positive():
            self._credit_note(uow, payload, sale_id, return_id, folio, credito, entry_date,
                              branch_id)

        cogs = self.money(payload, "cogs_amount", currency, required=False)
        if cogs.is_positive():
            self._engine.post(
                uow, JournalType.INVENTORY, entry_date, f"Costo devuelto {folio}",
                PostingReference("sales", return_id, PostingPurpose.SALE_RETURN_COGS,
                                 new_uuid()),
                [LineSpec(profile.account_for("inventory_account_id"), debit=cogs,
                          description=f"Reingreso de inventario {folio}"),
                 LineSpec(profile.account_for("cost_of_sales_account_id"), credit=cogs,
                          description=f"Reversa de costo de venta {folio}")],
                currency_code=currency, branch_id=branch_id)
        return entry

    def _credit_note(self, uow, payload, sale_id, return_id, folio, amount, entry_date,
                     branch_id) -> None:
        receivable = None
        for document in uow.financial_documents.find_by_source("sales", sale_id):
            receivable = uow.receivables.find_by_document(document.id)
            if receivable is not None:
                break
        if receivable is None:
            raise FinanceDomainError(
                f"Devolución a crédito {folio}: la venta no tiene CxC que acreditar")
        receivable.apply_credit_note(amount)
        uow.receivables.update(receivable)
        uow.financial_documents.save(FinancialDocument.create(
            FinancialDocumentType.CREDIT_NOTE, f"NC-{folio}", entry_date, amount,
            "sales", return_id, new_uuid(), branch_id=branch_id,
            customer_id=str(payload.get("customer_id") or "") or None))
