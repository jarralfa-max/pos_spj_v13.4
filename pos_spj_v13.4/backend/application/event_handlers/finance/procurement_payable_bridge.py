"""ProcurementPayableBridgeHandler — PAYABLE_CREATED (procurement bounded context).

Procurement's three-way match (``MatchSupplierInvoiceUseCase`` /
``ReleaseInvoiceVarianceUseCase``) correctly emits
``ACCOUNT_PAYABLE_CREATE_REQUESTED`` -> (translator) -> ``PAYABLE_CREATED``,
and ``CreatePayableUseCase`` was fully implemented and tested — but nothing
subscribed it to this event. A matched supplier invoice therefore created no
``Payable``/``FinancialDocument`` at all in production; this closes that gap.

The payable (``CreatePayableUseCase.create_in``) and its recognition entry are
written in ONE ``FinanceUnitOfWork`` (audit d9f2bca F01): before, the use case
committed the CxP in its own transaction and the entry was posted afterwards,
so a posting failure (e.g. obligation 100 vs recognition 90) left a persisted
CxP with zero journal entries. Now that failure leaves nothing. Idempotent by
``operation_id`` (the same one Procurement used for the match/release).

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

from backend.application.event_handlers.finance.procurement_posting_policy import (
    purchase_debit_lines,
    purchase_issue_date,
)
from backend.application.services.finance.posting_engine import PostingEngine
from backend.application.use_cases.finance.payable_use_cases import CreatePayableUseCase
from backend.domain.finance.enums import JournalType, PostingPurpose
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork


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
        issue_date = purchase_issue_date(payload)
        branch_id = payload.get("branch_id") or None
        with FinanceUnitOfWork(self._connection) as uow:
            self._use_case.create_in(
                uow, supplier_id=supplier_id, amount=str(amount), currency_code=currency_code,
                document_number=document_number, issue_date=issue_date,
                due_date=_due_date(issue_date, payload), branch_id=branch_id,
                source_module="procurement", source_document_id=payload.get("document_id"),
                operation_id=operation_id)
            self._post_recognition_entry(
                uow, payload, document_number=document_number, amount=str(amount),
                currency_code=currency_code, issue_date=issue_date,
                operation_id=operation_id, branch_id=branch_id)

    def _post_recognition_entry(self, uow, payload: dict, *, document_number: str, amount: str,
                                currency_code: str, issue_date: date, operation_id: str,
                                branch_id: str | None) -> None:
        if not payload.get("nature_subtotals"):
            # payload predates the purchase_nature breakdown — never guess an
            # account. The ledger-vs-subledger close control reports the gap.
            return
        profile = uow.posting_profiles.find_effective("PURCHASE", issue_date,
                                                     branch_id=branch_id)
        if profile is None:
            raise FinanceDomainError(
                f"No hay perfil contable PURCHASE vigente en {issue_date.isoformat()}")
        total = Money.from_string(amount, currency_code)
        lines = purchase_debit_lines(profile, payload, currency_code=currency_code,
                                     label=f"CxP {document_number}", total=total)
        if not lines:
            return
        lines.append(LineSpec(profile.account_for("payable_account_id"), credit=total,
                              description=f"CxP proveedor {document_number}"))
        self._engine.post(
            uow, JournalType.PURCHASES, issue_date,
            f"Reconocimiento de CxP {document_number}",
            PostingReference("procurement", str(payload.get("document_id") or ""),
                             PostingPurpose.SUPPLIER_INVOICE, operation_id),
            lines, currency_code=currency_code, branch_id=branch_id,
        )


def _due_date(issue_date: date, payload: dict) -> date | None:
    """Fecha de factura + días de crédito del proveedor (decisión del usuario,
    2026-09-18). La cuenta por pagar nacía SIN vencimiento: no había forma de
    saber qué deuda vencía ni cuándo. Sin días informados (evento anterior al
    cambio), se deja sin vencimiento en vez de inventar uno."""
    from datetime import timedelta
    explicit = str(payload.get("due_date") or "").strip()
    if explicit:
        # Regularización (migración 340): la CxP se reconoce en un periodo
        # abierto, pero vence cuando vencía según la recepción original.
        try:
            return date.fromisoformat(explicit[:10])
        except ValueError:
            pass
    dias = payload.get("payment_term_days")
    if dias is None or dias == "":
        return None
    try:
        return issue_date + timedelta(days=max(0, int(dias)))
    except (TypeError, ValueError):
        return None


#: Compatibilidad: algunos llamadores importaban el nombre privado.
_issue_date = purchase_issue_date
