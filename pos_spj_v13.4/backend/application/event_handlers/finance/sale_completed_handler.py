"""SALE_COMPLETED handler — recognizes revenue, settlements, credit and COGS.

The sale event must present the settlement breakdown (§19): the sum of
settlements must equal the net total. Non-cash instruments (points, coupons,
vouchers, gift cards, store credit) settle against their recognized commercial
obligation — never against cash.

Audit d9f2bca F09: the business key of the WHOLE effect is the sale. The lines
are built first without touching any aggregate; the entry is posted (the engine
returns the existing one only if the content is identical, F10); and the side
effects (instrument redemptions, prepaid-voucher obligations, receivable) are
applied ONLY when this call created the entry. Reissuing the same sale with a
new event_id no longer redeems a voucher twice.
"""

from __future__ import annotations

from decimal import Decimal

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

        profile = self.resolve_profile(uow, "SALE", entry_date, branch_id=branch_id)
        already_posted = uow.journal_entries.find_by_posting_reference(
            "sales", sale_id, PostingPurpose.SALE_REVENUE) is not None
        lines: list[LineSpec] = []
        redemptions: list[tuple] = []
        prepaid: list[tuple] = []
        credit_amount = Money.zero(currency)

        for settlement in settlements:
            settlement_type = SettlementType(str(settlement["type"]))
            amount = Money.from_string(str(settlement["amount"]), currency)
            if amount.is_zero():
                continue
            if settlement_type is SettlementType.ON_CREDIT:
                credit_amount = credit_amount.add(amount)
                # El renglón por cobrar lleva al cliente (auxiliar de clientes y
                # exposición de crédito consolidada; arquitectura híbrida, Slice 6).
                lines.append(LineSpec(profile.account_for("receivable_account_id"),
                                      debit=amount, description=f"Venta a crédito {folio}",
                                      customer_id=payload.get("customer_id") or None))
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
                line, obligation = self._instrument_settlement_line(
                    uow, settlement, settlement_type, amount, entry_date, folio, branch_id)
                lines.append(line)
                redemptions.append((obligation, amount))
            else:
                raise FinanceDomainError(f"Tipo de liquidación no soportado: {settlement_type}")

        if discount.is_positive():
            lines.append(LineSpec(profile.account_for("discount_account_id"),
                                  debit=discount, description=f"Descuento venta {folio}"))
        revenue = gross.subtract(tax)
        # Vales prepagados vendidos (2026-10-03): su importe es pasivo del vale,
        # no ingreso; la obligación queda registrada para su canje.
        for pasivo in payload.get("liability_lines") or []:
            importe = Money.from_string(str(pasivo["amount"]), currency)
            if not importe.is_positive():
                continue
            tipo = CommercialInstrumentType(str(pasivo["instrument_type"]))
            perfil = self.resolve_profile(uow, tipo.value, entry_date, instrument_type=tipo,
                                          branch_id=branch_id)
            prepaid.append((tipo, str(pasivo["instrument_id"]), importe))
            lines.append(LineSpec(perfil.account_for("liability_account_id"), credit=importe,
                                  description=f"Vale prepagado vendido {folio}"))
            revenue = revenue.subtract(importe)
        if revenue.is_positive():
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

        if not already_posted:
            for obligation, amount in redemptions:
                obligation.redeem(amount)
                uow.commercial_obligations.update(obligation)
            if prepaid:
                from backend.application.services.finance.commercial_instrument_processor import (
                    CommercialInstrumentProcessor,
                )
                for tipo, instrument_id, importe in prepaid:
                    CommercialInstrumentProcessor().register_obligation(
                        uow, instrument_type=tipo, source_module="commercial_instruments",
                        source_instrument_id=instrument_id, amount=importe,
                        on_date=entry_date, operation_id=new_uuid(),
                        customer_id=payload.get("customer_id"), branch_id=branch_id)
            if credit_amount.is_positive():
                self._create_receivable(uow, payload, sale_id, folio, credit_amount,
                                        entry_date, branch_id, currency)

        cogs = self.money(payload, "cogs_total", currency, required=False)
        if not already_posted:
            self._record_profitability(uow, payload, entry, sale_id, entry_date, branch_id,
                                       currency, net_revenue=revenue.subtract(discount),
                                       discount=discount, cogs=cogs)
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
    @staticmethod
    def _record_profitability(uow, payload: dict, entry, sale_id: str, entry_date,
                              branch_id, currency: str, *, net_revenue: Money,
                              discount: Money, cogs: Money) -> None:
        """Hechos de rentabilidad (§33), uno por renglón de la venta. El ingreso
        neto y el descuento del asiento se prorratean por importe de renglón y el
        último absorbe el redondeo: la suma de los hechos cuadra con el mayor."""
        lines = [l for l in payload.get("lines") or [] if Decimal(str(l.get("amount") or "0"))]
        common = dict(fact_type="SALE", source_module="sales", source_document_id=sale_id,
                      journal_entry_id=entry.id, fact_date=entry_date.isoformat(),
                      branch_id=branch_id, customer_id=payload.get("customer_id"),
                      channel=payload.get("channel"), order_id=payload.get("order_id"),
                      route_id=payload.get("route_id"), category_id=None,
                      currency_code=currency, operation_id=str(payload["operation_id"]))
        if not lines:
            uow.profitability.record(
                **common, line_reference="sale", product_id=None, quantity="0",
                net_revenue=net_revenue.to_string(), discount=discount.to_string(),
                cost_of_sales=cogs.to_string(), direct_cost="0.00")
            return
        cent = Decimal("0.01")
        weights = [Decimal(str(l["amount"])) for l in lines]
        total_weight = sum(weights, Decimal("0"))
        remaining = {"revenue": net_revenue.amount, "discount": discount.amount,
                     "cost": cogs.amount}
        for index, (line, weight) in enumerate(zip(lines, weights)):
            last = index == len(lines) - 1
            share = {key: (remaining[key] if last else
                           (total * weight / total_weight).quantize(cent))
                     for key, total in (("revenue", net_revenue.amount),
                                        ("discount", discount.amount))}
            unit_cost = str(line.get("unit_cost") or "").strip()
            line_cost = (remaining["cost"] if last else
                         (Decimal(str(line.get("quantity") or "0")) * Decimal(unit_cost))
                         .quantize(cent) if unit_cost else Decimal("0.00"))
            remaining["revenue"] -= share["revenue"]
            remaining["discount"] -= share["discount"]
            remaining["cost"] -= line_cost
            uow.profitability.record(
                **common, line_reference=str(index), product_id=line.get("product_id"),
                quantity=str(line.get("quantity") or "0"),
                net_revenue=format(share["revenue"], "f"),
                discount=format(share["discount"], "f"),
                cost_of_sales=format(line_cost, "f"), direct_cost="0.00")

    def _instrument_settlement_line(self, uow, settlement: dict, settlement_type, amount,
                                    entry_date, folio, branch_id=None):
        """Línea de canje y la obligación que liquida. NO la modifica: el canje
        se aplica sólo si este evento crea el asiento (F09)."""
        instrument_id = str(settlement.get("instrument_id") or "")
        if not instrument_id:
            raise FinanceDomainError(
                f"Liquidación {settlement_type.value} sin instrument_id en venta {folio}"
            )
        # El vale trae su naturaleza (vale por devolución, saldo a favor,
        # promocional…): cada una tiene su perfil y su pasivo (2026-10-03).
        instrument_type = (CommercialInstrumentType(str(settlement["instrument_type"]))
                           if settlement.get("instrument_type")
                           else _INSTRUMENT_SETTLEMENTS[settlement_type])
        obligation = uow.commercial_obligations.find_by_instrument(instrument_type, instrument_id)
        if obligation is None:
            raise FinanceDomainError(
                f"No existe obligación reconocida para {instrument_type.value} "
                f"{instrument_id} (venta {folio}); Finanzas no puede liquidar un "
                "instrumento no reconocido"
            )
        instrument_profile = self.resolve_profile(
            uow, instrument_type.value, entry_date, instrument_type=instrument_type,
            branch_id=branch_id,
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
        return (LineSpec(instrument_profile.account_for(role), debit=amount,
                         description=f"Canje {instrument_type.value} venta {folio}"),
                obligation)

    def _create_receivable(self, uow, payload, sale_id, folio, credit_amount,
                           entry_date, branch_id, currency) -> None:
        customer_id = str(payload.get("customer_id") or "")
        if not customer_id:
            raise FinanceDomainError(
                f"Venta a crédito {folio} sin customer_id; la CxC no puede omitirse"
            )
        # El POS ya registra el documento y la CxC al cobrar a crédito
        # (`SalesCreditClient.register`, que además alimenta el límite de
        # crédito). Crearla otra vez aquí duplicaría la deuda del cliente; este
        # manejador sólo aporta el ASIENTO, que aquélla no hace (Fase 6).
        for doc in uow.financial_documents.find_by_source("sales", sale_id):
            if doc.document_type is not FinancialDocumentType.CUSTOMER_INVOICE:
                continue
            existing = uow.receivables.find_by_document(doc.id)
            if existing is not None and existing.original_amount.amount != credit_amount.amount:
                # Auditoría F03: exposición (auxiliar) y contabilización deben
                # coincidir. Si no, la diferencia queda como excepción del
                # periodo y bloquea su cierre; la venta no se pierde.
                from backend.application.services.finance.close_controls import (
                    CHECK_SALE_CREDIT,
                )
                uow.close_exceptions.open_or_refresh(
                    period_code=entry_date.strftime("%Y-%m"), check_type=CHECK_SALE_CREDIT,
                    subject=f"{folio}:{sale_id}",
                    expected=credit_amount.to_string(),
                    actual=existing.original_amount.to_string(),
                    difference=credit_amount.subtract(existing.original_amount).to_string(),
                    currency_code=currency)
            return
        document = FinancialDocument.create(
            FinancialDocumentType.CUSTOMER_INVOICE, folio, entry_date, credit_amount,
            "sales", sale_id, new_uuid(),
            branch_id=branch_id, customer_id=customer_id,
        )
        uow.financial_documents.save(document)
        receivable = Receivable.create(
            customer_id, document.id, credit_amount, entry_date, new_uuid(),
            branch_id=branch_id,
        )
        uow.receivables.save(receivable)
