"""Asiento manual: captura y corrección del borrador (§8.3).

Un asiento manual nace BORRADOR con folio provisional (``BOR-…``, no consume
el consecutivo del diario), se corrige mientras es borrador, se valida
(cuadra) y se contabiliza aparte (``PostJournalEntryUseCase``) — con la
segregación de funciones que diga la configuración. Puede cancelarse mientras
no esté contabilizado; ya contabilizado sólo se corrige con reverso.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.application.services.finance.posting_engine import (
    PostingEngine,
    publish_finance_event,
)
from backend.domain.finance.entities.journal_entry import JournalEntry
from backend.domain.finance.enums import (
    AuditAction,
    FinancialDocumentType,
    FiscalPeriodStatus,
    JournalEntryStatus,
    JournalType,
    PostingPurpose,
)
from backend.domain.finance.exceptions import (
    ClosedFiscalPeriodError,
    FinanceConfigurationError,
    FinanceDomainError,
    JournalEntryNotFoundError,
)
from backend.domain.finance.services.journal_posting_service import (
    JournalPostingService,
    LineSpec,
)
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid

#: Diarios en los que se captura a mano (los automáticos los alimentan los handlers).
MANUAL_JOURNALS = frozenset({JournalType.GENERAL, JournalType.ADJUSTMENTS,
                             JournalType.OPENING, JournalType.CLOSING})

_DIMENSIONS = ("cost_center_id", "profit_center_id", "branch_id", "project_id",
               "department_id", "customer_id", "supplier_id", "employee_id", "product_id")


def line_specs_from_input(lines: list[dict], currency_code: str) -> list[LineSpec]:
    """``[{"account_id", "debit"|"credit": "123.45", "description"?, dimensiones?}]``."""
    specs: list[LineSpec] = []
    for raw in lines:
        debit = str(raw.get("debit") or "").strip()
        credit = str(raw.get("credit") or "").strip()
        if bool(debit) == bool(credit):
            raise FinanceDomainError(
                "Cada renglón lleva importe en débito o en crédito, nunca en ambos")
        specs.append(LineSpec(
            str(raw["account_id"]),
            debit=Money.from_string(debit, currency_code) if debit else None,
            credit=Money.from_string(credit, currency_code) if credit else None,
            description=str(raw.get("description") or "").strip(),
            source_reference=str(raw.get("source_reference") or "").strip(),
            **{name: (raw.get(name) or None) for name in _DIMENSIONS},
        ))
    return specs


def _period_for_draft(uow: FinanceUnitOfWork, entry_date: date):
    period = PostingEngine().resolve_period(uow, entry_date)
    if period.status is FiscalPeriodStatus.CLOSED:
        raise ClosedFiscalPeriodError(
            f"El periodo {period.period.code()} está cerrado; no admite asientos")
    return period


def _build_lines(uow: FinanceUnitOfWork, journal_id: str, period, entry_date: date,
                 description: str, reference: PostingReference, specs: list[LineSpec],
                 currency_code: str, exchange_rate, branch_id) -> JournalEntry:
    settings = uow.settings
    return JournalPostingService().build_entry(
        journal_id, "BOR-TMP", entry_date, period, description, reference, specs,
        currency_code=currency_code, base_currency_code=settings.base_currency_code,
        exchange_rate=PostingEngine.rate_for(uow, currency_code, settings.base_currency_code,
                                             entry_date, exchange_rate),
        rounding_account_id=settings.rounding_account_id, branch_id=branch_id,
        validate=False)


class CreateJournalEntryUseCase:
    def execute(self, connection, *, entry_date: date, description: str, lines: list[dict],
                operation_id: str, created_by: str, currency_code: str = "MXN",
                journal_type: JournalType = JournalType.GENERAL,
                exchange_rate: Decimal | str | None = None,
                branch_id: str | None = None) -> JournalEntry:
        if journal_type not in MANUAL_JOURNALS:
            raise FinanceDomainError(
                f"El diario {journal_type.value} lo alimentan los módulos operativos; "
                "un asiento manual va al diario General, Ajustes, Apertura o Cierre")
        if not (description or "").strip():
            raise FinanceDomainError("El asiento requiere descripción")
        currency_code = currency_code.upper()
        specs = line_specs_from_input(lines, currency_code)
        with FinanceUnitOfWork(connection) as uow:
            duplicate = uow.journal_entries.find_by_operation_id(operation_id)
            if duplicate is not None:
                return duplicate
            journal = uow.journals.get_by_type(journal_type)
            if journal is None:
                raise FinanceConfigurationError(f"El diario {journal_type.value} no existe")
            period = _period_for_draft(uow, entry_date)
            reference = PostingReference("finance", new_uuid(), PostingPurpose.MANUAL,
                                         operation_id)
            entry = _build_lines(uow, journal.id, period, entry_date, description.strip(),
                                 reference, specs, currency_code, exchange_rate, branch_id)
            entry.entry_number = f"BOR-{entry.id[-8:].upper()}"
            entry.created_by = created_by
            entry.source_document_type = FinancialDocumentType.MANUAL_ADJUSTMENT.value
            uow.journal_entries.save(entry)
            uow.audit(AuditAction.JOURNAL_ENTRY_CREATED, entity_type="journal_entry",
                      entity_id=entry.id, operation_id=operation_id, user_id=created_by,
                      after=_summary(entry), branch_id=branch_id)
            publish_finance_event(uow, EventName.JOURNAL_ENTRY_CREATED, {
                "journal_entry_id": entry.id, "entry_number": entry.entry_number,
                "status": entry.status.value,
            }, operation_id=operation_id, entity_id=entry.id, branch_id=branch_id)
            return entry


class UpdateJournalEntryDraftUseCase:
    """Corrige un borrador (o un validado, que vuelve a borrador)."""

    def execute(self, connection, *, journal_entry_id: str, operation_id: str,
                updated_by: str, lines: list[dict] | None = None,
                description: str | None = None, entry_date: date | None = None,
                exchange_rate: Decimal | str | None = None) -> JournalEntry:
        with FinanceUnitOfWork(connection) as uow:
            entry = _load(uow, journal_entry_id)
            before = _summary(entry)
            if entry.status is JournalEntryStatus.VALIDATED:
                entry.return_to_draft()
            new_date = entry_date or entry.entry_date
            period = _period_for_draft(uow, new_date)
            specs = (line_specs_from_input(lines, entry.currency_code) if lines is not None
                     else None)
            if specs is not None or entry_date is not None or exchange_rate is not None:
                source = specs if specs is not None else _specs_from_entry(entry)
                rebuilt = _build_lines(uow, entry.journal_id, period, new_date,
                                       entry.description, entry.posting_reference, source,
                                       entry.currency_code, exchange_rate, entry.branch_id)
                entry.replace_lines(rebuilt.lines)
            if description is not None:
                if not description.strip():
                    raise FinanceDomainError("El asiento requiere descripción")
                entry.description = description.strip()
            entry.entry_date = new_date
            entry.posting_date = new_date
            entry.fiscal_period_id = period.id
            uow.journal_entries.update_draft(entry)
            uow.audit(AuditAction.JOURNAL_ENTRY_CREATED, entity_type="journal_entry",
                      entity_id=entry.id, operation_id=operation_id, user_id=updated_by,
                      before=before, after=_summary(entry), reason="Corrección de borrador")
            return entry


class CancelJournalEntryUseCase:
    def execute(self, connection, *, journal_entry_id: str, reason: str, operation_id: str,
                cancelled_by: str) -> JournalEntry:
        if not (reason or "").strip():
            raise FinanceDomainError("Cancelar un asiento exige el motivo")
        with FinanceUnitOfWork(connection) as uow:
            entry = _load(uow, journal_entry_id)
            before = _summary(entry)
            entry.cancel(cancelled_by, reason)
            uow.journal_entries.update_draft(entry)
            uow.audit(AuditAction.JOURNAL_ENTRY_CANCELLED, entity_type="journal_entry",
                      entity_id=entry.id, operation_id=operation_id, user_id=cancelled_by,
                      before=before, after=_summary(entry), reason=reason)
            return entry


def _load(uow: FinanceUnitOfWork, journal_entry_id: str) -> JournalEntry:
    entry = uow.journal_entries.get(journal_entry_id)
    if entry is None:
        raise JournalEntryNotFoundError("El asiento no existe")
    return entry


def _specs_from_entry(entry: JournalEntry) -> list[LineSpec]:
    return [LineSpec(line.account_id,
                     debit=line.debit if line.debit.is_positive() else None,
                     credit=line.credit if line.credit.is_positive() else None,
                     description=line.description, source_reference=line.source_reference,
                     **{name: getattr(line, name) for name in _DIMENSIONS})
            for line in entry.lines if line.line_role.value == "NORMAL"]


def _summary(entry: JournalEntry) -> dict:
    return {
        "entry_number": entry.entry_number, "status": entry.status.value,
        "entry_date": entry.entry_date.isoformat(), "description": entry.description,
        "currency_code": entry.currency_code,
        "debits": entry.base_total_debits().to_string(),
        "credits": entry.base_total_credits().to_string(),
        "lines": [{"account_id": l.account_id, "debit": l.debit.to_string(),
                   "credit": l.credit.to_string()} for l in entry.lines],
    }
