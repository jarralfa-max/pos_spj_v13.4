"""PostingEngine — the single application path that writes to the ledger.

Responsibilities:
- idempotency: an ``operation_id`` or ``(source_module, source_document_id,
  posting_purpose)`` already posted returns the existing entry (no double effects)
  ONLY when the request carries the same economic content (accounts, amounts,
  currency, dimensions); the same key with different content raises
  ``IdempotencyConflictError`` instead of passing for success (audit F10);
- currency: every line is in the entry currency; foreign-currency entries carry
  their exchange rate and base amounts, and any conversion rounding goes to the
  configured rounding account, visibly (§24);
- fiscal period resolution (auto-opens the period if it does not exist yet;
  posting into SOFT_CLOSED needs the special permission, CLOSED always fails);
- gap-free entry numbering per journal;
- transactional outbox publication of JOURNAL_ENTRY_POSTED / _REVERSED.

No operational module may write to journal_entries/journal_lines directly.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from decimal import Decimal

from backend.domain.finance.entities.fiscal_period import FiscalPeriod
from backend.domain.finance.entities.journal_entry import JournalEntry
from backend.domain.finance.enums import JournalType, PostingPurpose
from backend.domain.finance.exceptions import (
    AccountNotFoundError,
    ClosedFiscalPeriodError,
    CurrencyMismatchError,
    FinanceConfigurationError,
    IdempotencyConflictError,
    JournalEntryAlreadyReversedError,
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

_FINGERPRINT_DIMENSIONS = ("cost_center_id", "branch_id", "profit_center_id", "project_id",
                           "department_id", "customer_id", "supplier_id", "employee_id",
                           "product_id")


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
        currency_code: str | None = None,
        exchange_rate: Decimal | None = None,
        branch_id: str | None = None,
        created_by: str | None = None,
        source_document_type: str | None = None,
        allow_soft_closed: bool = False,
    ) -> JournalEntry:
        """Post one balanced entry. Idempotent: a repeat with the same content
        returns the original; the same key with other content is a conflict."""
        currency_code = self._entry_currency(line_specs, currency_code)
        requested = self.fingerprint(line_specs, currency_code)
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
            return self._same_content_or_conflict(existing, requested)
        existing_op = uow.journal_entries.find_by_operation_id(posting_reference.operation_id)
        if existing_op is not None:
            return self._same_content_or_conflict(existing_op, requested)

        self._validate_accounts(uow, line_specs)
        journal = uow.journals.get_by_type(journal_type)
        if journal is None:
            raise FinanceConfigurationError(
                f"El diario {journal_type.value} no existe; falta la configuración inicial")
        period = self.resolve_period(uow, entry_date)
        settings = uow.settings
        entry = self._domain.build_entry(
            journal_id=journal.id,
            entry_number=uow.journals.next_entry_number(journal),
            entry_date=entry_date,
            fiscal_period=period,
            description=description,
            posting_reference=posting_reference,
            line_specs=line_specs,
            currency_code=currency_code,
            base_currency_code=settings.base_currency_code,
            exchange_rate=self.rate_for(uow, currency_code, settings.base_currency_code,
                                     entry_date, exchange_rate),
            rounding_account_id=settings.rounding_account_id,
            branch_id=branch_id,
            created_by=created_by,
            source_document_type=source_document_type,
        )
        self._domain.post(entry, period, posted_by=created_by,
                          allow_soft_closed=allow_soft_closed)
        uow.journal_entries.save(entry)
        self._publish(uow, EventName.JOURNAL_ENTRY_POSTED, entry)
        return entry

    # ── asiento manual ya validado (§8.3) ────────────────────────────────
    def post_existing(self, uow: FinanceUnitOfWork, entry: JournalEntry, *,
                      posted_by: str, allow_soft_closed: bool = False) -> JournalEntry:
        """Contabiliza un asiento manual VALIDADO: recibe su número definitivo
        del diario (el provisional del borrador no consume folio) y queda
        inmutable."""
        self._validate_accounts_for_entry(uow, entry)
        period = self.resolve_period(uow, entry.posting_date)
        journal = uow.journals.get(entry.journal_id)
        if journal is None:
            raise FinanceConfigurationError("El diario del asiento no existe")
        entry.entry_number = uow.journals.next_entry_number(journal)
        entry.fiscal_period_id = period.id
        self._domain.post(entry, period, posted_by=posted_by,
                          allow_soft_closed=allow_soft_closed)
        uow.journal_entries.update_draft_to_posted(entry)
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
        """Reverse a POSTED entry. Idempotent per ``operation_id``: repeating
        the SAME reversal returns it; a second, different reversal of an entry
        already reversed is rejected (JournalEntryAlreadyReversedError)."""
        duplicate = uow.journal_entries.find_by_operation_id(operation_id)
        if duplicate is not None:
            if duplicate.reversal_of_entry_id == original_entry.id:
                return duplicate
            raise IdempotencyConflictError(
                f"La operación {operation_id} ya se usó para otro asiento")
        if original_entry.reversed_by_entry_id:
            existing = uow.journal_entries.get(original_entry.reversed_by_entry_id)
            if existing is not None and posting_purpose is not None \
                    and existing.posting_reference.posting_purpose is posting_purpose:
                # Un flujo de integración (p. ej. cancelar una venta) repite su
                # propio reverso con otra operación: el efecto ya existe.
                return existing
            raise JournalEntryAlreadyReversedError(
                f"El asiento {original_entry.entry_number} ya fue revertido "
                f"({existing.entry_number if existing else original_entry.reversed_by_entry_id})")

        journal = uow.journals.get(original_entry.journal_id)
        if journal is None:
            raise FinanceConfigurationError("El diario del asiento original no existe")
        period = self.resolve_period(uow, reversal_date)
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
        self._domain.post_reversal(original_entry, reversal, period, posted_by=created_by)
        uow.journal_entries.save(reversal)
        uow.journal_entries.update_status(original_entry)
        self._publish(uow, EventName.JOURNAL_ENTRY_REVERSED, reversal)
        return reversal

    # ── idempotency / currency (audit F06, F10) ───────────────────────────
    @staticmethod
    def _entry_currency(line_specs: list[LineSpec], currency_code: str | None) -> str:
        currencies = {
            amount.currency_code
            for spec in line_specs
            for amount in (spec.debit, spec.credit)
            if amount is not None and not amount.is_zero()
        }
        if len(currencies) > 1:
            raise CurrencyMismatchError(
                f"Un asiento lleva una sola moneda de operación: {sorted(currencies)}")
        if currency_code is None:
            return currencies.pop() if currencies else "MXN"
        if currencies and currencies != {currency_code.upper()}:
            raise CurrencyMismatchError(
                f"Las líneas están en {currencies.pop()} y el asiento en {currency_code}")
        return currency_code.upper()

    @staticmethod
    def rate_for(uow: FinanceUnitOfWork, currency_code: str, base_currency_code: str,
              on_date: date, explicit: Decimal | None) -> Decimal | None:
        if currency_code == base_currency_code:
            return explicit
        if explicit is not None:
            return Decimal(str(explicit))
        record = uow.currencies.rate_on(currency_code, base_currency_code, on_date)
        return record.rate if record is not None else None

    @staticmethod
    def fingerprint(line_specs: list[LineSpec], currency_code: str) -> tuple:
        """Contenido económico canónico: moneda + multiconjunto de líneas
        (cuenta, debe, haber, dimensiones). Fecha y descripción no cuentan."""
        rows = []
        for spec in line_specs:
            for amount, side in ((spec.debit, "D"), (spec.credit, "C")):
                if amount is not None and amount.is_positive():
                    rows.append((spec.account_id, side, amount.to_string())
                                + tuple(getattr(spec, d) or "" for d in _FINGERPRINT_DIMENSIONS))
        return (currency_code.upper(), tuple(sorted(rows)))

    @staticmethod
    def _entry_fingerprint(entry: JournalEntry) -> tuple:
        rows = []
        for line in entry.lines:
            if line.line_role.value != "NORMAL":
                continue
            for amount, side in ((line.debit, "D"), (line.credit, "C")):
                if amount is not None and amount.is_positive():
                    rows.append((line.account_id, side, amount.to_string())
                                + tuple(getattr(line, d) or "" for d in _FINGERPRINT_DIMENSIONS))
        return (str(entry.currency_code).upper(), tuple(sorted(rows)))

    def _same_content_or_conflict(self, existing: JournalEntry, requested: tuple) -> JournalEntry:
        if self._entry_fingerprint(existing) != requested:
            raise IdempotencyConflictError(
                f"La operación {existing.posting_reference.operation_id} ya se contabilizó "
                f"(asiento {existing.entry_number}) con otro contenido; no se sobrescribe "
                "ni se devuelve como éxito")
        return existing

    # ── helpers ───────────────────────────────────────────────────────────
    def resolve_period(self, uow: FinanceUnitOfWork, entry_date: date) -> FiscalPeriod:
        period = uow.fiscal_periods.find_for_date(entry_date)
        if period is None:
            # Auditoría F16: el periodo se abre solo para fechas NUEVAS. Abrir
            # en silencio un mes anterior a uno ya cerrado reabriría por la
            # puerta de atrás un pasado que el cierre declaró terminado.
            code = (entry_date.year, entry_date.month)
            for later in uow.fiscal_periods.list_all():
                if (later.period.year, later.period.month) > code \
                        and later.status.value in ("SOFT_CLOSED", "CLOSED"):
                    raise ClosedFiscalPeriodError(
                        f"No se abre {entry_date.year:04d}-{entry_date.month:02d}: hay un "
                        f"periodo posterior cerrado ({later.period.code()})")
            period = FiscalPeriod.open_for(entry_date.year, entry_date.month)
            uow.fiscal_periods.save(period)
            self._publish_raw(uow, EventName.FISCAL_PERIOD_OPENED, {
                "fiscal_period_id": period.id,
                "period": period.period.code(),
            }, operation_id=new_uuid(), entity_id=period.id)
        return period

    @staticmethod
    def _validate_accounts(uow: FinanceUnitOfWork, line_specs: list[LineSpec]) -> None:
        for spec in line_specs:
            account = uow.accounts.get(spec.account_id)
            if account is None:
                raise AccountNotFoundError(f"La cuenta {spec.account_id} no existe")
            account.assert_postable(branch_id=spec.branch_id)

    @staticmethod
    def _validate_accounts_for_entry(uow: FinanceUnitOfWork, entry: JournalEntry) -> None:
        for line in entry.lines:
            account = uow.accounts.get(line.account_id)
            if account is None:
                raise AccountNotFoundError(f"La cuenta {line.account_id} no existe")
            account.assert_postable(branch_id=line.branch_id or entry.branch_id)

    def _publish(self, uow: FinanceUnitOfWork, event_name: EventName, entry: JournalEntry) -> None:
        self._publish_raw(uow, event_name, {
            "journal_entry_id": entry.id,
            "entry_number": entry.entry_number,
            "entry_date": entry.entry_date.isoformat(),
            "posting_date": entry.posting_date.isoformat(),
            "source_module": entry.posting_reference.source_module,
            "source_document_id": entry.posting_reference.source_document_id,
            "posting_purpose": entry.posting_reference.posting_purpose.value,
            "total_debits": entry.base_total_debits().to_string(),
            "total_credits": entry.base_total_credits().to_string(),
            "currency_code": entry.currency_code,
            "base_currency_code": entry.base_currency_code,
            "branch_id": entry.branch_id,
        }, operation_id=entry.posting_reference.operation_id, entity_id=entry.id,
            branch_id=entry.branch_id)

    @staticmethod
    def _publish_raw(uow: FinanceUnitOfWork, event_name: EventName, payload: dict,
                     *, operation_id: str, entity_id: str | None = None,
                     branch_id: str | None = None) -> None:
        publish_finance_event(uow, event_name, payload, operation_id=operation_id,
                              entity_id=entity_id, branch_id=branch_id)


def publish_finance_event(uow: FinanceUnitOfWork, event_name: EventName, payload: dict, *,
                          operation_id: str, entity_id: str | None = None,
                          branch_id: str | None = None,
                          source_document_id: str | None = None) -> str:
    """Encola un evento financiero con el sobre canónico (§27): ``event_id``,
    ``operation_id``, ``entity_id``, ``occurred_at``, ``source_module``,
    ``source_document_id`` y ``branch_id`` — distintos entre sí. Se publica
    después de la persistencia: lo entrega el despachador del outbox."""
    from datetime import datetime, timezone
    event_id = new_uuid()
    envelope = dict(payload)
    envelope.setdefault("event_id", event_id)
    envelope["event_id"] = event_id
    envelope["event_name"] = event_name.value
    envelope["operation_id"] = operation_id
    envelope["entity_id"] = entity_id or payload.get("entity_id") or operation_id
    envelope["occurred_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    envelope.setdefault("source_module", "finance")
    envelope["source_document_id"] = (source_document_id or payload.get("source_document_id")
                                      or envelope["entity_id"])
    envelope["branch_id"] = branch_id if branch_id is not None else payload.get("branch_id")
    uow.outbox.enqueue(
        event_id=event_id,
        event_name=event_name.value,
        payload_json=json.dumps(envelope, ensure_ascii=False, default=str),
        operation_id=operation_id,
    )
    return event_id
