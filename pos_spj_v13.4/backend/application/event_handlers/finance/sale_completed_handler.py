"""SALE_COMPLETED handler — recognizes revenue, settlements, credit and COGS.

The sale event must present the settlement breakdown (§19): the sum of
settlements must equal the net total. Non-cash instruments (points, coupons,
vouchers, gift cards, store credit) settle against their recognized commercial
obligation — never against cash.
"""

from __future__ import annotations

from backend.application.event_handlers.finance.handler_base import FinanceEventHandler
from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.entities.financial_document import FinancialDocument
from backend.domain.finance.entities.receivable import Receivable
from backend.domain.finance.enums import (
    CommercialInstrumentType,
    FinancialDocumentType,
    JournalType,
    PostingPurpose,
    RecognitionBasis,
    SettlementType,
)
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.shared.ids import new_uuid

_INSTRUMENT_SETTLEMENTS: dict[SettlementType, CommercialInstrumentType] = {
    SettlementType.LOYALTY_POINTS: CommercialInstrumentType.LOYALTY_POINTS,
    SettlementType.GIFT_CARD: CommercialInstrumentType.GIFT_CARD,
    SettlementType.VOUCHER: CommercialInstrumentType.REFUND_VOUCHER,
    SettlementType.COUPON: CommercialInstrumentType.PROMOTIONAL_COUPON,
    SettlementType.STORE_CREDIT: CommercialInstrumentType.STORE_CREDIT,
    SettlementType.PROMOTIONAL_BALANCE: CommercialInstrumentType.PROMOTIONAL_BALANCE,
}


class SaleCompletedHandler(FinanceEventHandler):
    event_name = "SALE_COMPLETED"

    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._engine = PostingEngine()

    def _handle(self, uow, payload: dict) -> None:
        currency = self.currency(payload)
        sale_id = str(payload.get("sale_id") or "")
        if not sale_id:
            raise FinanceDomainError("SALE_COMPLETED sin sale_id")
        entry_date = self.event_date(payload)
        branch_id = payload.get("branch_id")
        folio = str(payload.get("folio") or sale_id[:8])

        gross = self.money(payload, "gross_total", currency)
        discount = self.money(payload, "discount_total", currency, required=False)
        net = self.money(payload, "net_total", currency)
        tax = self.money(payload, "tax_total", currency, required=False)
        if gross.subtract(discount).amount != net.amount:
            raise FinanceDomainError(
                f"Venta {folio}: gross - discount != net "
                f"({gross.to_string()} - {discount.to_string()} != {net.to_string()})"
            )

        settlements = payload.get("settlements") or []
        settled_total = Money.zero(currency)
        for settlement in settlements:
            settled_total = settled_total.add(
                Money.from_string(str(settlement["amount"]), currency)
            )
        if settled_total.amount != net.amount:
            raise FinanceDomainError(
                f"Venta {folio}: la suma de liquidaciones {settled_total.to_string()} "
                f"no coincide con el total a cubrir {net.to_string()}"
            )

        profile = self.resolve_profile(uow, "SALE", entry_date)
        lines: list[LineSpec] = []
        credit_amount = Money.zero(currency)

        for settlement in settlements:
            settlement_type = SettlementType(str(settlement["type"]))
            amount = Money.from_string(str(settlement["amount"]), currency)
            if amount.is_zero():
                continue
            if settlement_type is SettlementType.ON_CREDIT:
                credit_amount = credit_amount.add(amount)
                lines.append(LineSpec(profile.account_for("receivable_account_id"),
                                      debit=amount, description=f"Venta a crédito {folio}"))
            elif settlement_type is SettlementType.CASH:
                lines.append(LineSpec(profile.account_for("cash_account_id"),
                                      debit=amount, description=f"Efectivo venta {folio}"))
            elif settlement_type is SettlementType.BANK_TRANSFER:
                lines.append(LineSpec(profile.account_for("bank_account_id"),
                                      debit=amount, description=f"Transferencia venta {folio}"))
            elif settlement_type in (SettlementType.CARD, SettlementType.PAYMENT_PROCESSOR):
                lines.append(LineSpec(profile.account_for("clearing_account_id"),
                                      debit=amount, description=f"Tarjeta/procesador venta {folio}"))
            elif settlement_type in _INSTRUMENT_SETTLEMENTS:
                lines.append(self._instrument_settlement_line(
                    uow, settlement, settlement_type, amount, entry_date, folio))
            else:
                raise FinanceDomainError(f"Tipo de liquidación no soportado: {settlement_type}")

        if discount.is_positive():
            lines.append(LineSpec(profile.account_for("discount_account_id"),
                                  debit=discount, description=f"Descuento venta {folio}"))
        revenue = gross.subtract(tax)
        lines.append(LineSpec(profile.account_for("revenue_account_id"),
                              credit=revenue, description=f"Ingreso venta {folio}"))
        if tax.is_positive():
            lines.append(LineSpec(profile.account_for("tax_account_id"),
                                  credit=tax, description=f"IVA trasladado venta {folio}"))

        entry = self._engine.post(
            uow, JournalType.SALES, entry_date, f"Venta {folio}",
            PostingReference("sales", sale_id, PostingPurpose.SALE_REVENUE,
                             str(payload["operation_id"])),
            lines, currency_code=currency, branch_id=branch_id,
        )

        if credit_amount.is_positive():
            self._create_receivable(uow, payload, sale_id, folio, credit_amount,
                                    entry_date, branch_id, currency)

        cogs = self.money(payload, "cogs_total", currency, required=False)
        if cogs.is_positive():
            self._engine.post(
                uow, JournalType.INVENTORY, entry_date, f"Costo de venta {folio}",
                PostingReference("sales", sale_id, PostingPurpose.SALE_COGS, new_uuid()),
                [
                    LineSpec(profile.account_for("cost_of_sales_account_id"), debit=cogs,
                             description=f"COGS venta {folio}"),
                    LineSpec(profile.account_for("inventory_account_id"), credit=cogs,
                             description=f"Salida de inventario venta {folio}"),
                ],
                currency_code=currency, branch_id=branch_id,
            )
        return entry

    # ── helpers ───────────────────────────────────────────────────────────
    def _instrument_settlement_line(self, uow, settlement: dict,
                                    settlement_type, amount, entry_date, folio) -> LineSpec:
        instrument_id = str(settlement.get("instrument_id") or "")
        if not instrument_id:
            raise FinanceDomainError(
                f"Liquidación {settlement_type.value} sin instrument_id en venta {folio}"
            )
        instrument_type = _INSTRUMENT_SETTLEMENTS[settlement_type]
        obligation = uow.commercial_obligations.find_by_instrument(instrument_type, instrument_id)
        if obligation is None:
            raise FinanceDomainError(
                f"No existe obligación reconocida para {instrument_type.value} "
                f"{instrument_id} (venta {folio}); Finanzas no puede liquidar un "
                "instrumento no reconocido"
            )
        obligation.redeem(amount)
        uow.commercial_obligations.update(obligation)
        instrument_profile = self.resolve_profile(
            uow, instrument_type.value, entry_date, instrument_type=instrument_type,
        )
        if obligation.recognition_basis is RecognitionBasis.NO_INITIAL_RECOGNITION:
            role = "contra_revenue_account_id"
        elif (instrument_type is CommercialInstrumentType.GIFT_CARD
              and instrument_profile.has_account("gift_card_liability_account_id")):
            role = "gift_card_liability_account_id"
        elif obligation.recognition_basis is RecognitionBasis.PROMOTIONAL_EXPENSE:
            role = "promotional_balance_account_id"
        else:
            role = "liability_account_id"
        return LineSpec(instrument_profile.account_for(role), debit=amount,
                        description=f"Canje {instrument_type.value} venta {folio}")

    def _create_receivable(self, uow, payload, sale_id, folio, credit_amount,
                           entry_date, branch_id, currency) -> None:
        customer_id = str(payload.get("customer_id") or "")
        if not customer_id:
            raise FinanceDomainError(
                f"Venta a crédito {folio} sin customer_id; la CxC no puede omitirse"
            )
        document = FinancialDocument.create(
            FinancialDocumentType.SALES_INVOICE, folio, entry_date, credit_amount,
            "sales", sale_id, new_uuid(),
            branch_id=branch_id, customer_id=customer_id,
        )
        uow.financial_documents.save(document)
        receivable = Receivable.create(
            customer_id, document.id, credit_amount, entry_date, new_uuid(),
            branch_id=branch_id,
        )
        uow.receivables.save(receivable)
