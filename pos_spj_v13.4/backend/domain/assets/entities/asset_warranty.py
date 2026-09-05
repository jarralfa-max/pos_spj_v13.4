"""AssetWarranty — manufacturer/provider warranty coverage (ASSET-9, §40).

Reuses ``AssetWarrantyStatus`` (defined in enums.py since ASSET-3, where it
already lived on the Asset aggregate's summary field).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from backend.domain.assets.enums import AssetWarrantyStatus
from backend.domain.assets.exceptions import AssetDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class AssetWarranty:
    id: str
    asset_id: str
    provider_id: str
    warranty_type: str
    starts_at: date
    expires_at: date
    operation_id: str
    coverage: str = ""
    document_id: str | None = None
    status: AssetWarrantyStatus = AssetWarrantyStatus.ACTIVE
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, asset_id: str, provider_id: str, warranty_type: str, starts_at: date,
               expires_at: date, operation_id: str, *, coverage: str = "",
               document_id: str | None = None) -> "AssetWarranty":
        if not asset_id or not provider_id:
            raise AssetDomainError("AssetWarranty requires asset_id and provider_id")
        if expires_at <= starts_at:
            raise AssetDomainError("AssetWarranty.expires_at must be after starts_at")
        return cls(id=new_uuid(), asset_id=asset_id, provider_id=provider_id,
                    warranty_type=warranty_type, starts_at=starts_at, expires_at=expires_at,
                    operation_id=operation_id, coverage=coverage, document_id=document_id)

    def is_expiring(self, *, within_days: int = 30, as_of: date | None = None) -> bool:
        today = as_of or date.today()
        return self.status is AssetWarrantyStatus.ACTIVE and \
            today <= self.expires_at <= today + timedelta(days=within_days)

    def refresh_status(self, *, as_of: date | None = None) -> None:
        """Recompute ACTIVE/EXPIRING/EXPIRED from the dates — VOID is never
        auto-derived, it's an explicit action via void()."""
        if self.status is AssetWarrantyStatus.VOID:
            return
        today = as_of or date.today()
        if today > self.expires_at:
            self.status = AssetWarrantyStatus.EXPIRED
        elif self.is_expiring(as_of=today):
            self.status = AssetWarrantyStatus.EXPIRING
        else:
            self.status = AssetWarrantyStatus.ACTIVE

    def void(self, reason: str = "") -> None:
        self.status = AssetWarrantyStatus.VOID
        if reason:
            self.coverage = f"{self.coverage}\n[VOID] {reason}".strip()
