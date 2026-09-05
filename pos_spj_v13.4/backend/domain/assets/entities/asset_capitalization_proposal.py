"""AssetCapitalizationProposal — Activos PROPOSES capitalization, Finance decides
and posts (ASSET-10, §30-31, §68).

State machine:

    DRAFT -> SUBMITTED -> UNDER_REVIEW -> APPROVED -> POSTED
                                        -> REJECTED
    DRAFT | SUBMITTED -> CANCELLED

``approve()``/``reject()``/``mark_posted()`` only RECORD that a decision
arrived from Finance (via an event Activos' own application layer consumes
in a later phase) — they never call the finance posting engine or any
finance/treasury service themselves. Activos owns the proposal record; Finance owns
the actual accounting treatment (`CapitalizeAssetUseCase` in
`backend/application/use_cases/finance/capital_and_asset_use_cases.py`,
already built and PRESERVEd — see docs/refactor/assets_finance_boundary_map.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.assets.enums import AssetCapitalizationProposalStatus
from backend.domain.assets.exceptions import (
    AssetCapitalizationProposalInvalidError,
    AssetDomainError,
)
from backend.domain.finance.value_objects.money import Money
from backend.shared.ids import new_uuid

_TERMINAL = frozenset({
    AssetCapitalizationProposalStatus.POSTED,
    AssetCapitalizationProposalStatus.REJECTED,
    AssetCapitalizationProposalStatus.CANCELLED,
})


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class AssetCapitalizationProposal:
    id: str
    asset_id: str
    improvement_id: str
    proposed_amount: Money
    justification: str
    submitted_by: str
    operation_id: str
    status: AssetCapitalizationProposalStatus = AssetCapitalizationProposalStatus.DRAFT
    reviewed_by: str | None = None
    decision_notes: str = ""
    financial_reference: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, asset_id: str, improvement_id: str, proposed_amount: Money,
               justification: str, submitted_by: str, operation_id: str) -> "AssetCapitalizationProposal":
        if not asset_id or not improvement_id:
            raise AssetDomainError(
                "AssetCapitalizationProposal requires asset_id and improvement_id")
        if not proposed_amount.is_positive():
            raise AssetDomainError("AssetCapitalizationProposal.proposed_amount must be positive")
        if not justification or not justification.strip():
            raise AssetDomainError("AssetCapitalizationProposal.justification is required")
        if not submitted_by:
            raise AssetDomainError("AssetCapitalizationProposal.submitted_by is required")
        return cls(id=new_uuid(), asset_id=asset_id, improvement_id=improvement_id,
                    proposed_amount=proposed_amount, justification=justification.strip(),
                    submitted_by=submitted_by, operation_id=operation_id)

    def _assert_status(self, *allowed: AssetCapitalizationProposalStatus) -> None:
        if self.status not in allowed:
            raise AssetCapitalizationProposalInvalidError(
                f"No se puede continuar la propuesta en estado {self.status.value}")

    def submit(self) -> None:
        self._assert_status(AssetCapitalizationProposalStatus.DRAFT)
        self.status = AssetCapitalizationProposalStatus.SUBMITTED
        self.updated_at = _utcnow()

    def begin_review(self) -> None:
        self._assert_status(AssetCapitalizationProposalStatus.SUBMITTED)
        self.status = AssetCapitalizationProposalStatus.UNDER_REVIEW
        self.updated_at = _utcnow()

    def approve(self, reviewed_by: str, decision_notes: str = "") -> None:
        self._assert_status(AssetCapitalizationProposalStatus.UNDER_REVIEW)
        if not reviewed_by:
            raise AssetDomainError("AssetCapitalizationProposal.approve requires a reviewer")
        self.reviewed_by = reviewed_by
        self.decision_notes = decision_notes
        self.status = AssetCapitalizationProposalStatus.APPROVED
        self.updated_at = _utcnow()

    def reject(self, reviewed_by: str, decision_notes: str = "") -> None:
        self._assert_status(AssetCapitalizationProposalStatus.UNDER_REVIEW)
        if not reviewed_by:
            raise AssetDomainError("AssetCapitalizationProposal.reject requires a reviewer")
        self.reviewed_by = reviewed_by
        self.decision_notes = decision_notes
        self.status = AssetCapitalizationProposalStatus.REJECTED
        self.updated_at = _utcnow()

    def mark_posted(self, financial_reference: str) -> None:
        """Records that Finance already posted this — never posts itself."""
        self._assert_status(AssetCapitalizationProposalStatus.APPROVED)
        if not financial_reference:
            raise AssetDomainError("AssetCapitalizationProposal.mark_posted requires a reference")
        self.financial_reference = financial_reference
        self.status = AssetCapitalizationProposalStatus.POSTED
        self.updated_at = _utcnow()

    def cancel(self, reason: str = "") -> None:
        if self.status in _TERMINAL:
            raise AssetCapitalizationProposalInvalidError(
                f"No se puede cancelar una propuesta en estado {self.status.value}")
        self.status = AssetCapitalizationProposalStatus.CANCELLED
        if reason:
            self.decision_notes = f"{self.decision_notes}\n[CANCELLED] {reason}".strip()
        self.updated_at = _utcnow()
