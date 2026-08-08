"""ProcurementPayableBridgeHandler — PAYABLE_CREATED (procurement bounded context).

Procurement's three-way match (``MatchSupplierInvoiceUseCase`` /
``ReleaseInvoiceVarianceUseCase``) correctly emits
``ACCOUNT_PAYABLE_CREATE_REQUESTED`` -> (translator) -> ``PAYABLE_CREATED``,
and ``CreatePayableUseCase`` was fully implemented and tested — but nothing
subscribed it to this event. A matched supplier invoice therefore created no
``Payable``/``FinancialDocument`` at all in production; this closes that gap.

Delegates entirely to ``CreatePayableUseCase``, which opens its own
``FinanceUnitOfWork`` and is idempotent by ``operation_id`` (the same
``operation_id`` Procurement used for the match/release), so no separate
event-level dedup is needed here.

Also posts the recognition entry (Debit Inventario/Gasto/Activo per
``purchase_nature`` — Credit CxP) — CLAUDE.md §11 requires every financial
impact to carry a balanced journal entry, and creating the obligation is one.
The event carries ``nature_subtotals`` (pre-tax subtotal per purchase_nature,
built by ``SupplierInvoiceLine.purchase_nature`` — see MIGRATION_LOG.md);
older/legacy payloads without it are only supported through the payable
creation, never guessed into a journal entry.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.application.services.finance.posting_engine import PostingEngine
from backend.application.use_cases.finance.payable_use_cases import CreatePayableUseCase
from backend.domain.finance.enums import JournalType, PostingPurpose
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork

#: purchase_nature -> posting-profile account role. SERVICE has no dedicated
#: role in the chart of accounts; a purchased service is an operating expense.
_NATURE_ACCOUNT_ROLE = {
    "INVENTORY": "inventory_account_id",
    "EXPENSE": "expense_account_id",
    "ASSET": "asset_account_id",
    "SERVICE": "expense_account_id",
}


class ProcurementPayableBridgeHandler:
    event_name = "PAYABLE_CREATED"

    def __init__(self, connection, use_case: CreatePayableUseCase | None = None) -> None:
        self._connection = connection
        self._use_case = use_case or CreatePayableUseCase()
        self._engine = PostingEngine()

    def handle(self, payload: dict) -> None:
        if str(payload.get("source_module") or "") != "procurement":
            return  # PAYABLE_CREATED may originate from other sources later
        supplier_id = str(payload.get("supplier_id") or "").strip()
        document_number = str(payload.get("document_number") or "").strip()
        amount = payload.get("amount")
        operation_id = str(payload.get("operation_id") or "").strip()
        if not supplier_id or not document_number or not amount or not operation_id:
            raise FinanceDomainError(
                "PAYABLE_CREATED (procurement) requiere supplier_id, document_number, "
                "amount y operation_id")
        currency_code = str(payload.get("currency_code") or "MXN")
        issue_date = _issue_date(payload)
        payable = self._use_case.execute(
            self._connection, supplier_id=supplier_id, amount=str(amount),
            currency_code=currency_code,
            document_number=document_number, issue_date=issue_date,
            branch_id=payload.get("branch_id") or None, source_module="procurement",
            source_document_id=payload.get("document_id"), operation_id=operation_id)
        self._post_recognition_entry(
            payload, document_number=document_number, amount=str(amount),
            currency_code=currency_code, issue_date=issue_date, operation_id=operation_id)

    def _post_recognition_entry(self, payload: dict, *, document_number: str, amount: str,
                                currency_code: str, issue_date: date,
                                operation_id: str) -> None:
        nature_subtotals: dict = payload.get("nature_subtotals") or {}
        if not nature_subtotals:
            # payload predates the purchase_nature breakdown (or every line was
            # captured before this fix) — never guess an account, just skip.
            return
        document_id = str(payload.get("document_id") or "")
        with FinanceUnitOfWork(self._connection) as uow:
            profile = uow.posting_profiles.find_effective("PURCHASE", issue_date)
            if profile is None:
                raise FinanceDomainError(
                    f"No hay perfil contable PURCHASE vigente en {issue_date.isoformat()}")
            lines: list[LineSpec] = []
            debited = Decimal("0")
            for nature, subtotal in nature_subtotals.items():
                money = Money.from_string(str(subtotal), currency_code)
                if not money.is_positive():
                    continue
                role = _NATURE_ACCOUNT_ROLE.get(nature, "expense_account_id")
                lines.append(LineSpec(profile.account_for(role), debit=money,
                                      description=f"CxP {document_number} ({nature})"))
                debited += money.amount
            tax_total = Money.from_string(str(payload.get("tax_total") or "0"), currency_code)
            if tax_total.is_positive():
                lines.append(LineSpec(profile.account_for("tax_account_id"), debit=tax_total,
                                      description=f"IVA acreditable {document_number}"))
                debited += tax_total.amount
            if not lines:
                return
            total = Money.from_string(amount, currency_code)
            if debited != total.amount:
                raise FinanceDomainError(
                    f"CxP {document_number}: subtotales por naturaleza + impuesto "
                    f"({debited}) != total de la factura ({total.amount})")
            lines.append(LineSpec(profile.account_for("payable_account_id"), credit=total,
                                  description=f"CxP proveedor {document_number}"))
            self._engine.post(
                uow, JournalType.PURCHASES, issue_date,
                f"Reconocimiento de CxP {document_number}",
                PostingReference("procurement", document_id, PostingPurpose.SUPPLIER_INVOICE,
                                 operation_id),
                lines, currency_code=currency_code, branch_id=payload.get("branch_id") or None,
            )


def _issue_date(payload: dict) -> date:
    timestamp = str(payload.get("timestamp") or "")
    if timestamp:
        try:
            return date.fromisoformat(timestamp[:10])
        except ValueError:
            pass
    return date.today()
