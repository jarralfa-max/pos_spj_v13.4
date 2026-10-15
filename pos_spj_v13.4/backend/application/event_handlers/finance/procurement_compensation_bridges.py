"""Compensaciones financieras de Compras (auditoría Compras d9f2bca C12).

Antes cambiar el estado del documento de compra no compensaba nada: un reverso
de compra de contado dejaba su asiento de pago intacto y una devolución
confirmada no tocaba la CxP. Estos dos consumidores cierran ese hueco.

- ``ProcurementImmediatePaymentReversalHandler`` — DIRECT_PURCHASE_REVERSED de
  una compra de CONTADO: revierte el asiento «compra de contado» (cargo a
  inventario/gasto contra tesorería). Una compra a crédito no tiene asiento en
  Compras (su deuda nace con la factura), y Compras ya impide reversar una
  compra facturada.
- ``ProcurementReturnCreditHandler`` — PURCHASE_RETURN_CONFIRMED: el valor de lo
  devuelto (más su IVA) se aplica como nota de crédito a la CxP de la factura
  del origen (Dr Proveedores / Cr Inventario, Cr IVA acreditable). Lo que exceda el saldo de la CxP (ya pagada,
  o compra de contado) queda como ANTICIPO del proveedor (Dr Anticipos a
  proveedores / Cr Inventario): un saldo a favor visible, no un número suelto.
  Mercancía aún no facturada no lleva asiento: su factura deberá venir por menos
  (la conciliación descuenta lo devuelto de lo aceptado).

Ambos idempotentes por la referencia de contabilización del documento.
"""

from __future__ import annotations

from backend.application.event_handlers.finance.procurement_posting_policy import (
    NATURE_ACCOUNT_ROLE,
    purchase_issue_date,
)
from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.enums import FinancialDocumentType, JournalType, PostingPurpose
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork


class ProcurementImmediatePaymentReversalHandler:
    event_name = "DIRECT_PURCHASE_REVERSED"

    def __init__(self, connection) -> None:
        self._connection = connection
        self._engine = PostingEngine()

    def handle(self, payload: dict) -> None:
        document_id = str(payload.get("document_id") or "").strip()
        operation_id = str(payload.get("operation_id") or "").strip()
        if not document_id or not operation_id:
            raise FinanceDomainError("DIRECT_PURCHASE_REVERSED requiere document_id y operation_id")
        with FinanceUnitOfWork(self._connection) as uow:
            entry = uow.journal_entries.find_by_posting_reference(
                "procurement", document_id, PostingPurpose.SUPPLIER_PAYMENT)
            if entry is None or entry.reversed_by_entry_id:
                return  # crédito (sin asiento) o ya revertido
            self._engine.reverse(
                uow, entry, purchase_issue_date(payload),
                str(payload.get("reason") or "Reverso de compra de contado"),
                f"{operation_id}:payment-reversal",
                created_by=payload.get("user_id"))


class ProcurementReturnCreditHandler:
    """Crédito contra la CxP de una compra. Atiende la devolución confirmada y,
    desde 2026-10-15, ``PURCHASE_PAYABLE_CREDIT_REQUESTED`` (reverso de una
    recepción a crédito ya reconocida, o factura menor a lo recibido): mismo
    efecto, Dr Proveedores (o anticipo si ya se pagó) / Cr lo reconocido."""

    event_name = "PURCHASE_RETURN_CONFIRMED"

    def _goods_credit_lines(self, uow, profile, payload, goods, currency, on_date, folio):
        """El abono sale por NATURALEZA si el evento trae el desglose (un gasto
        no se acredita a inventario); si no, todo a inventario, como siempre."""
        natures = payload.get("nature_subtotals") or {}
        if natures:
            purchase = uow.posting_profiles.find_effective(
                "PURCHASE", on_date, branch_id=payload.get("branch_id") or None)
            if purchase is not None:
                from decimal import Decimal
                lines, credited = [], Decimal("0")
                for nature, value in natures.items():
                    amount = Money.from_string(str(value), currency)
                    if not amount.is_positive():
                        continue
                    role = NATURE_ACCOUNT_ROLE.get(nature, "expense_account_id")
                    lines.append(LineSpec(purchase.account_for(role), credit=amount,
                                          description=f"{folio} ({nature})"))
                    credited += amount.amount
                if lines and credited == goods.amount:
                    return lines
        return [LineSpec(profile.account_for("inventory_account_id"), credit=goods,
                         description=f"Devolución a proveedor {folio}")]

    def __init__(self, connection) -> None:
        self._connection = connection
        self._engine = PostingEngine()

    def handle(self, payload: dict) -> None:
        return_id = str(payload.get("document_id") or "").strip()
        operation_id = str(payload.get("operation_id") or "").strip()
        value = str(payload.get("return_value") or "0")
        tax_value = str(payload.get("return_tax") or "0")
        currency = str(payload.get("currency_code") or "MXN")
        invoice_ids = [str(i) for i in payload.get("invoice_ids") or []]
        if not return_id or not operation_id:
            raise FinanceDomainError(
                "PURCHASE_RETURN_CONFIRMED requiere document_id y operation_id")
        goods = Money.from_string(value, currency)
        tax = Money.from_string(tax_value, currency)
        total = goods.add(tax)   # la CxP de la factura incluye el IVA
        if not total.is_positive() or not invoice_ids:
            return  # sin valor o sin facturar: no hay efecto financiero
        on_date = purchase_issue_date(payload)
        with FinanceUnitOfWork(self._connection) as uow:
            if uow.journal_entries.find_by_posting_reference(
                    "procurement", return_id, PostingPurpose.SUPPLIER_CREDIT_NOTE) is not None:
                return
            profile = uow.posting_profiles.find_effective(
                "PURCHASE_RETURN", on_date, branch_id=payload.get("branch_id") or None)
            if profile is None:
                raise FinanceDomainError("No hay perfil contable PURCHASE_RETURN vigente")
            remaining = total
            credited = Money.zero(currency)
            for invoice_id in invoice_ids:
                if not remaining.is_positive():
                    break
                for document in uow.financial_documents.find_by_source("procurement",
                                                                       invoice_id):
                    if document.document_type is not FinancialDocumentType.SUPPLIER_INVOICE:
                        continue
                    payable = uow.payables.find_by_document(document.id)
                    if payable is None or not payable.outstanding_amount.is_positive():
                        continue
                    applied = (remaining if remaining <= payable.outstanding_amount
                               else payable.outstanding_amount)
                    payable.apply_credit_note(applied)
                    uow.payables.update(payable)
                    document.apply_settlement(applied)
                    uow.financial_documents.update(document)
                    credited = credited.add(applied)
                    remaining = remaining.subtract(applied)
            folio = str(payload.get("document_number") or return_id[:8])
            lines = []
            if credited.is_positive():
                lines.append(LineSpec(profile.account_for("payable_account_id"), debit=credited,
                                      description=f"Nota de crédito {folio}"))
            if remaining.is_positive():
                lines.append(LineSpec(profile.account_for("supplier_advance_account_id"),
                                      debit=remaining,
                                      description=f"Saldo a favor con proveedor {folio}"))
            lines += self._goods_credit_lines(uow, profile, payload, goods, currency,
                                              on_date, folio)
            if tax.is_positive():
                lines.append(LineSpec(profile.account_for("tax_account_id"), credit=tax,
                                      description=f"IVA acreditable devuelto {folio}"))
            self._engine.post(
                uow, JournalType.PURCHASES, on_date, f"Devolución a proveedor {folio}",
                PostingReference("procurement", return_id, PostingPurpose.SUPPLIER_CREDIT_NOTE,
                                 operation_id),
                lines, currency_code=currency, branch_id=payload.get("branch_id") or None,
                created_by=payload.get("user_id"))
