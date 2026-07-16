"""PostingEngine — the single application path that writes to the ledger.

Responsibilities:
- idempotency: an ``operation_id`` or ``(source_module, source_document_id,
  posting_purpose)`` already posted returns the existing entry (no double effects);
- fiscal period resolution (auto-opens the period if it does not exist yet;
  posting into SOFT_CLOSED/CLOSED periods always fails);
- gap-free entry numbering per journal;
- transactional outbox publication of JOURNAL_ENTRY_POSTED / _REVERSED.

No operational module may write to journal_entries/journal_lines directly.
"""

from __future__ import annotations

import json
import logging
from datetime import date

from backend.domain.finance.entities.fiscal_period import FiscalPeriod
from backend.domain.finance.entities.journal_entry import JournalEntry
from backend.domain.finance.enums import JournalType, PostingPurpose
from backend.domain.finance.exceptions import (
    DuplicateOperationError,
    FinanceDomainError,
)
from backend.domain.finance.services.journal_posting_service import (
    JournalPostingService,
    LineSpec,
)
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.finance.posting_engine")


class PostingEngine:
    def __init__(self) -> None:
        self._domain = JournalPostingService()

    # ── posting ───────────────────────────────────────────────────────────
    def post(
        self,
        uow: FinanceUnitOfWork,
        journal_type: JournalType,
        entry_date: date,
        description: str,
        posting_reference: PostingReference,
        line_specs: list[LineSpec],
        *,
        currency_code: str = "MXN",
        branch_id: str | None = None,
        created_by: str | None = None,
    ) -> JournalEntry:
        """Post one balanced entry. Idempotent: a repeat returns the original."""
        existing = uow.journal_entries.find_by_posting_reference(
            posting_reference.source_module,
            posting_reference.source_document_id,
            posting_reference.posting_purpose,
        )
        if existing is not None:
            logger.info("PostingEngine: idempotent hit for %s/%s/%s",
                        posting_reference.source_module,
                        posting_reference.source_document_id,
                        posting_reference.posting_purpose.value)
            return existing
        existing_op = uow.journal_entries.find_by_operation_id(posting_reference.operation_id)
        if existing_op is not None:
            return existing_op

        self._validate_accounts(uow, line_specs)
        journal = uow.journals.get_by_type(journal_type)
        if journal is None:
            raise FinanceDomainError(f"Journal {journal_type.value} does not exist; run the bootstrap")
        period = self._resolve_period(uow, entry_date)
        entry_number = uow.journals.next_entry_number(journal)
        entry = self._domain.build_entry(
            journal_id=journal.id,
            entry_number=entry_number,
            entry_date=entry_date,
            fiscal_period=period,
            description=description,
            posting_reference=posting_reference,
            line_specs=line_specs,
            currency_code=currency_code,
            branch_id=branch_id,
            created_by=created_by,
        )
        self._domain.post(entry, period)
        uow.journal_entries.save(entry)
        self._publish(uow, EventName.JOURNAL_ENTRY_POSTED, entry)
        return entry

    # ── reversal ──────────────────────────────────────────────────────────
    def reverse(
        self,
        uow: FinanceUnitOfWork,
        original_entry: JournalEntry,
        reversal_date: date,
        reason: str,
        operation_id: str,
        *,
        posting_purpose: PostingPurpose | None = None,
        created_by: str | None = None,
    ) -> JournalEntry:
        """Reverse a POSTED entry. Idempotent: an already-reversed entry returns
        its reversal instead of creating a second one."""
        if original_entry.reversed_by_entry_id:
            existing = uow.journal_entries.get(original_entry.reversed_by_entry_id)
            if existing is not None:
                return existing
        duplicate = uow.journal_entries.find_by_operation_id(operation_id)
        if duplicate is not None:
            return duplicate

        journal = uow.journals.get(original_entry.journal_id)
        if journal is None:
            raise FinanceDomainError("Original journal not found")
        period = self._resolve_period(uow, reversal_date)
        reference = PostingReference(
            source_module=original_entry.posting_reference.source_module,
            source_document_id=original_entry.id,
            posting_purpose=posting_purpose or PostingPurpose.REVERSAL,
            operation_id=operation_id,
        )
        reversal = self._domain.build_reversal(
            original_entry,
            reversal_entry_number=uow.journals.next_entry_number(journal),
            reversal_date=reversal_date,
            fiscal_period=period,
            reason=reason,
            posting_reference=reference,
            created_by=created_by,
        )
        self._domain.post_reversal(original_entry, reversal, period)
        uow.journal_entries.save(reversal)
        uow.journal_entries.update_status(original_entry)
        self._publish(uow, EventName.JOURNAL_ENTRY_REVERSED, reversal)
        return reversal

    # ── helpers ───────────────────────────────────────────────────────────
    def _resolve_period(self, uow: FinanceUnitOfWork, entry_date: date) -> FiscalPeriod:
        period = uow.fiscal_periods.find_for_date(entry_date)
        if period is None:
            period = FiscalPeriod.open_for(entry_date.year, entry_date.month)
            uow.fiscal_periods.save(period)
            self._publish_raw(uow, EventName.FISCAL_PERIOD_OPENED, {
                "fiscal_period_id": period.id,
                "period": period.period.code(),
            }, operation_id=new_uuid())
        return period

    @staticmethod
    def _validate_accounts(uow: FinanceUnitOfWork, line_specs: list[LineSpec]) -> None:
        for spec in line_specs:
            account = uow.accounts.get(spec.account_id)
            if account is None:
                raise FinanceDomainError(f"Account {spec.account_id} does not exist")
            account.assert_postable()

    def _publish(self, uow: FinanceUnitOfWork, event_name: EventName, entry: JournalEntry) -> None:
        self._publish_raw(uow, event_name, {
            "journal_entry_id": entry.id,
            "entry_number": entry.entry_number,
            "entry_date": entry.entry_date.isoformat(),
            "source_module": entry.posting_reference.source_module,
            "source_document_id": entry.posting_reference.source_document_id,
            "posting_purpose": entry.posting_reference.posting_purpose.value,
            "total_debits": entry.total_debits().to_string(),
            "total_credits": entry.total_credits().to_string(),
            "currency_code": entry.currency_code,
            "branch_id": entry.branch_id,
        }, operation_id=entry.posting_reference.operation_id)

    @staticmethod
    def _publish_raw(uow: FinanceUnitOfWork, event_name: EventName, payload: dict,
                     *, operation_id: str) -> None:
        uow.outbox.enqueue(
            event_id=new_uuid(),
            event_name=event_name.value,
            payload_json=json.dumps(payload, ensure_ascii=False),
            operation_id=operation_id,
        )
