"""AssetInsurancePolicy — insurance coverage for an asset (ASSET-9, §41).

Activos tracks the policy for operational/documentary purposes only — it
never manages the policy's accounting treatment (§41: "No gestionar póliza
contablemente").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from backend.domain.assets.enums import AssetInsuranceStatus
from backend.domain.assets.exceptions import AssetDomainError
from backend.domain.finance.value_objects.money import Money
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class AssetInsurancePolicy:
    id: str
    asset_id: str
    provider: str
    policy_number: str
    insured_value: Money
    starts_at: date
    expires_at: date
    operation_id: str
    coverage: str = ""
    document_reference: str | None = None
    status: AssetInsuranceStatus = AssetInsuranceStatus.ACTIVE
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, asset_id: str, provider: str, policy_number: str, insured_value: Money,
               starts_at: date, expires_at: date, operation_id: str, *,
               coverage: str = "", document_reference: str | None = None) -> "AssetInsurancePolicy":
        if not asset_id or not provider or not policy_number:
            raise AssetDomainError(
                "AssetInsurancePolicy requires asset_id, provider and policy_number")
        if not insured_value.is_positive():
            raise AssetDomainError("AssetInsurancePolicy.insured_value must be positive")
        if expires_at <= starts_at:
            raise AssetDomainError("AssetInsurancePolicy.expires_at must be after starts_at")
        return cls(id=new_uuid(), asset_id=asset_id, provider=provider,
                    policy_number=policy_number, insured_value=insured_value,
                    starts_at=starts_at, expires_at=expires_at, operation_id=operation_id,
                    coverage=coverage, document_reference=document_reference)

    def cancel(self, reason: str = "") -> None:
        if self.status is AssetInsuranceStatus.CANCELLED:
            raise AssetDomainError("Esta póliza ya está cancelada")
        self.status = AssetInsuranceStatus.CANCELLED
        if reason:
            self.coverage = f"{self.coverage}\n[CANCELLED] {reason}".strip()

    def refresh_status(self, *, as_of: date | None = None) -> None:
        if self.status is AssetInsuranceStatus.CANCELLED:
            return
        today = as_of or date.today()
        if today > self.expires_at:
            self.status = AssetInsuranceStatus.EXPIRED
        else:
            self.status = AssetInsuranceStatus.ACTIVE
