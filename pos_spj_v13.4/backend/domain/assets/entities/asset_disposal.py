"""AssetDisposal — physical evidence of an executed disposal (ASSET-12, §46-47).

Activos documents the physical disposition only. Accounting value, resulting
gain/loss and the journal entry belong to Finance (`DisposeAssetUseCase` in
`backend/application/use_cases/finance/capital_and_asset_use_cases.py`,
already built and PRESERVEd) — this entity never computes or records any of
that, only what physically happened and the evidence for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.assets.enums import AssetDisposalReason
from backend.domain.assets.exceptions import AssetDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class AssetDisposal:
    id: str
    disposal_request_id: str
    asset_id: str
    reason: AssetDisposalReason
    executed_by: str
    operation_id: str
    evidence_reference: str | None = None
    notes: str = ""
    executed_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, disposal_request_id: str, asset_id: str, reason: AssetDisposalReason,
               executed_by: str, operation_id: str, *,
               evidence_reference: str | None = None, notes: str = "") -> "AssetDisposal":
        if not disposal_request_id or not asset_id:
            raise AssetDomainError("AssetDisposal requires disposal_request_id and asset_id")
        if not executed_by:
            raise AssetDomainError("AssetDisposal.executed_by is required")
        return cls(id=new_uuid(), disposal_request_id=disposal_request_id, asset_id=asset_id,
                    reason=reason, executed_by=executed_by, operation_id=operation_id,
                    evidence_reference=evidence_reference, notes=notes)
