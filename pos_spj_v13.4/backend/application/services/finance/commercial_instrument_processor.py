"""CommercialInstrumentProcessor — canonical recognition pipeline for every
commercial instrument (points, coupons, vouchers, gift cards, stored value).

Finance recognizes economic effects only. The owning module (Loyalty,
Promotions, …) keeps the operational master; ``source_instrument_id``
references that identity. Nothing here validates commercial rules.
"""

from __future__ import annotations

import json
import logging
from datetime import date

from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.entities.commercial_obligation import CommercialObligation
from backend.domain.finance.enums import (
    CommercialInstrumentType,
    JournalType,
    PostingPurpose,
    RecognitionBasis,
)
from backend.domain.finance.exceptions import (
    FinanceDomainError,
    PostingProfileNotFoundError,
)
from backend.domain.finance.policies.commercial_instrument_posting_policy import (
    CommercialInstrumentPostingPolicy,
)
from backend.domain.finance.services.commercial_instrument_accounting_service import (
    CommercialInstrumentAccountingService,
)
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.finance.instruments")

_LOYALTY_JOURNAL = {CommercialInstrumentType.LOYALTY_POINTS: JournalType.LOYALTY}


class CommercialInstrumentProcessor:
    def __init__(self) -> None:
        self._engine = PostingEngine()
        self._accounting = CommercialInstrumentAccountingService()
        self._policy = CommercialInstrumentPostingPolicy()

    # ── recognition (issue / sell / grant) ────────────────────────────────
    def recognize(
        self,
        uow: FinanceUnitOfWork,
        *,
        instrument_type: CommercialInstrumentType,
        source_module: str,
        source_instrument_id: str,
        amount: Money,
        on_date: date,
        operation_id: str,
        customer_id: str | None = None,
        branch_id: str | None = None,
        program_id: str | None = None,
        campaign_id: str | None = None,
        funding_party: str | None = None,
        expires_at: str | None = None,
        settlement_amount: Money | None = None,
    ) -> CommercialObligation:
        """Create (or return, idempotently) the obligation and post recognition."""
        existing = uow.commercial_obligations.find_by_instrument(
            instrument_type, source_instrument_id)
        if existing is not None:
            return existing
        duplicate = uow.commercial_obligations.find_by_operation_id(operation_id)
        if duplicate is not None:
            return duplicate

        profile = self._find_profile(uow, instrument_type, on_date,
                                     program_id=program_id, campaign_id=campaign_id,
                                     branch_id=branch_id, funding_party=funding_party)
        basis = self._policy.recognition_basis_for(
            instrument_type, funding_party=funding_party)
        obligation = CommercialObligation.recognize(
            instrument_type, source_module, source_instrument_id, basis, amount,
            operation_id, customer_id=customer_id, branch_id=branch_id,
            issued_at=on_date.isoformat(), expires_at=expires_at,
        )
        uow.commercial_obligations.save(obligation)

        lines = self._accounting.recognition_lines(
            obligation, profile, settlement_amount=settlement_amount)
        if lines:
            self._engine.post(
                uow, self._journal_for(instrument_type), on_date,
                f"Reconocimiento {instrument_type.value} {source_instrument_id[:8]}",
                PostingReference("commercial_instruments",
                                 f"{instrument_type.value}:{source_instrument_id}",
                                 PostingPurpose.INSTRUMENT_RECOGNITION, new_uuid()),
                lines, currency_code=amount.currency_code, branch_id=branch_id,
            )
        self._emit(uow, EventName.COMMERCIAL_OBLIGATION_RECOGNIZED, obligation, operation_id)
        return obligation

    # ── reload (gift card top-up) ─────────────────────────────────────────
    def reload(self, uow: FinanceUnitOfWork, *, instrument_type: CommercialInstrumentType,
               source_instrument_id: str, amount: Money, on_date: date,
               operation_id: str) -> CommercialObligation:
        obligation = self._require_obligation(uow, instrument_type, source_instrument_id)
        duplicate = uow.journal_entries.find_by_operation_id(operation_id)
        if duplicate is not None:
            return obligation
        obligation.increase_recognition(amount)
        uow.commercial_obligations.update(obligation)
        profile = self._find_profile(uow, instrument_type, on_date)
        from backend.domain.finance.services.journal_posting_service import LineSpec

        # recognition_lines values the full recognized amount; a reload posts
        # only the top-up amount on the same accounts.
        rebuilt = [
            LineSpec(spec.account_id,
                     debit=amount if spec.debit is not None else None,
                     credit=amount if spec.credit is not None else None,
                     description=spec.description)
            for spec in self._accounting.recognition_lines(
                obligation, profile, settlement_amount=amount)
        ]
        self._engine.post(
            uow, self._journal_for(instrument_type), on_date,
            f"Recarga {instrument_type.value} {source_instrument_id[:8]}",
            PostingReference("commercial_instruments",
                             f"{instrument_type.value}:{source_instrument_id}:reload:{operation_id}",
                             PostingPurpose.INSTRUMENT_RECOGNITION, operation_id),
            rebuilt, currency_code=amount.currency_code, branch_id=obligation.branch_id,
        )
        return obligation

    # ── redemption ────────────────────────────────────────────────────────
    def redeem(
        self,
        uow: FinanceUnitOfWork,
        *,
        instrument_type: CommercialInstrumentType,
        source_instrument_id: str,
        amount: Money,
        on_date: date,
        operation_id: str,
        redemption_id: str | None = None,
        actual_cost: Money | None = None,
    ) -> CommercialObligation:
        """Redeem against the obligation and post the configured effect.

        Standalone redemptions (outside a sale entry). Redemptions embedded in a
        sale settlement are posted by the sale handler instead.
        """
        obligation = self._require_obligation(uow, instrument_type, source_instrument_id)
        redemption_key = redemption_id or operation_id
        existing = uow.journal_entries.find_by_posting_reference(
            "commercial_instruments",
            f"{instrument_type.value}:{source_instrument_id}:redeem:{redemption_key}",
            PostingPurpose.INSTRUMENT_REDEMPTION,
        )
        if existing is not None:
            return obligation

        obligation.redeem(amount)
        uow.commercial_obligations.update(obligation)
        profile = self._find_profile(uow, instrument_type, on_date)
        lines = self._accounting.redemption_lines(obligation, profile, amount,
                                                  actual_cost=actual_cost)
        if lines:
            self._engine.post(
                uow, self._journal_for(instrument_type), on_date,
                f"Canje {instrument_type.value} {source_instrument_id[:8]}",
                PostingReference("commercial_instruments",
                                 f"{instrument_type.value}:{source_instrument_id}:redeem:{redemption_key}",
                                 PostingPurpose.INSTRUMENT_REDEMPTION, new_uuid()),
                lines, currency_code=amount.currency_code, branch_id=obligation.branch_id,
            )
        self._emit(uow, EventName.COMMERCIAL_OBLIGATION_REDEEMED, obligation, operation_id)
        return obligation

    # ── expiration (breakage) ─────────────────────────────────────────────
    def expire(self, uow: FinanceUnitOfWork, *, instrument_type: CommercialInstrumentType,
               source_instrument_id: str, on_date: date, operation_id: str,
               amount: Money | None = None) -> CommercialObligation:
        obligation = self._require_obligation(uow, instrument_type, source_instrument_id)
        existing = uow.journal_entries.find_by_posting_reference(
            "commercial_instruments",
            f"{instrument_type.value}:{source_instrument_id}",
            PostingPurpose.INSTRUMENT_EXPIRATION,
        )
        if existing is not None:
            return obligation
        released = obligation.release_by_expiration(amount)
        uow.commercial_obligations.update(obligation)
        profile = self._find_profile(uow, instrument_type, on_date)
        lines = self._accounting.expiration_lines(obligation, profile, released)
        if lines:
            self._engine.post(
                uow, self._journal_for(instrument_type), on_date,
                f"Expiración {instrument_type.value} {source_instrument_id[:8]}",
                PostingReference("commercial_instruments",
                                 f"{instrument_type.value}:{source_instrument_id}",
                                 PostingPurpose.INSTRUMENT_EXPIRATION, new_uuid()),
                lines, currency_code=released.currency_code, branch_id=obligation.branch_id,
            )
        self._emit(uow, EventName.COMMERCIAL_OBLIGATION_RELEASED, obligation, operation_id)
        return obligation

    # ── reversal ──────────────────────────────────────────────────────────
    def reverse(self, uow: FinanceUnitOfWork, *, instrument_type: CommercialInstrumentType,
                source_instrument_id: str, on_date: date, operation_id: str,
                reason: str = "Reverso de instrumento") -> CommercialObligation:
        """Reverses the recognition entry (mirror) and closes the obligation.
        The original entries are never edited."""
        obligation = self._require_obligation(uow, instrument_type, source_instrument_id)
        original = uow.journal_entries.find_by_posting_reference(
            "commercial_instruments",
            f"{instrument_type.value}:{source_instrument_id}",
            PostingPurpose.INSTRUMENT_RECOGNITION,
        )
        obligation.reverse()
        uow.commercial_obligations.update(obligation)
        if original is not None and not original.reversed_by_entry_id:
            self._engine.reverse(uow, original, on_date, reason, new_uuid(),
                                 posting_purpose=PostingPurpose.INSTRUMENT_REVERSAL)
        self._emit(uow, EventName.COMMERCIAL_OBLIGATION_REVERSED, obligation, operation_id)
        return obligation

    # ── helpers ───────────────────────────────────────────────────────────
    def _require_obligation(self, uow, instrument_type, source_instrument_id):
        obligation = uow.commercial_obligations.find_by_instrument(
            instrument_type, source_instrument_id)
        if obligation is None:
            raise FinanceDomainError(
                f"No existe obligación para {instrument_type.value} {source_instrument_id}"
            )
        return obligation

    @staticmethod
    def _find_profile(uow, instrument_type: CommercialInstrumentType, on_date: date,
                      **criteria):
        profile = uow.posting_profiles.find_effective(
            instrument_type.value, on_date, instrument_type=instrument_type, **criteria)
        if profile is None:
            raise PostingProfileNotFoundError(
                f"No hay perfil contable vigente para {instrument_type.value}; "
                "configúrelo antes de procesar el instrumento"
            )
        return profile

    @staticmethod
    def _journal_for(instrument_type: CommercialInstrumentType) -> JournalType:
        return _LOYALTY_JOURNAL.get(instrument_type, JournalType.COMMERCIAL_INSTRUMENTS)

    @staticmethod
    def _emit(uow, event_name: EventName, obligation: CommercialObligation,
              operation_id: str) -> None:
        uow.outbox.enqueue(
            event_id=new_uuid(),
            event_name=event_name.value,
            payload_json=json.dumps({
                "obligation_id": obligation.id,
                "instrument_type": obligation.instrument_type.value,
                "source_instrument_id": obligation.source_instrument_id,
                "status": obligation.status.value,
                "outstanding": obligation.outstanding_amount.to_string(),
                "currency_code": obligation.original_amount.currency_code,
            }),
            operation_id=operation_id,
        )
