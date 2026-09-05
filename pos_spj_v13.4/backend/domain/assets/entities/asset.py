"""Asset — the core EAM aggregate (§11, §16-17).

This is a DISTINCT entity from ``backend.domain.finance.entities.fixed_asset.
FixedAsset``. Asset owns the physical/operational lifecycle (classification,
location, custody, condition, status); FixedAsset owns accounting value and
depreciation. They correlate by id via events, never merge
(`docs/refactor/assets_finance_boundary_map.md`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from backend.domain.assets.enums import (
    AssetCondition,
    AssetCriticality,
    AssetOwnershipType,
    AssetStatus,
    AssetWarrantyStatus,
)
from backend.domain.assets.exceptions import AssetDomainError, AssetStateInvalidError
from backend.shared.ids import new_uuid

_TERMINAL_STATUSES = frozenset({
    AssetStatus.DISPOSED, AssetStatus.SOLD, AssetStatus.DONATED,
    AssetStatus.STOLEN, AssetStatus.LOST,
})

# §16: allowed status transitions for the domain-level lifecycle methods this
# phase implements (commission/suspend/reactivate). Later phases (custody,
# transfers, maintenance, disposal — ASSET-4..12) add their own guarded
# transitions on top of this table rather than opening it up generically.
_SUSPENDABLE_STATUSES = frozenset({
    AssetStatus.AVAILABLE, AssetStatus.ASSIGNED, AssetStatus.IN_USE, AssetStatus.LOANED,
})


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class Asset:
    id: str
    asset_number: str
    name: str
    asset_category_id: str
    operation_id: str
    description: str = ""
    manufacturer: str = ""
    model: str = ""
    serial_number: str | None = None
    acquisition_date: date | None = None
    commissioned_at: str | None = None
    origin_branch_id: str | None = None
    current_branch_id: str | None = None
    current_location_id: str | None = None
    custodian_user_id: str | None = None
    responsible_employee_id: str | None = None
    supplier_id: str | None = None
    purchase_reference_id: str | None = None
    financial_asset_id: str | None = None  # correlates to FixedAsset.id, read-only link
    status: AssetStatus = AssetStatus.DRAFT
    condition: AssetCondition = AssetCondition.NEW
    criticality: AssetCriticality = AssetCriticality.MEDIUM
    ownership_type: AssetOwnershipType = AssetOwnershipType.OWNED
    warranty_status: AssetWarrantyStatus = AssetWarrantyStatus.NONE
    expected_useful_life_months: int | None = None
    operational_start_date: date | None = None
    notes: str = ""
    created_by_user_id: str | None = None
    version: int = 1
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, asset_number: str, name: str, asset_category_id: str,
               operation_id: str, *, created_by_user_id: str | None = None,
               origin_branch_id: str | None = None,
               current_branch_id: str | None = None, **extra) -> "Asset":
        if not asset_number or not asset_number.strip():
            raise AssetDomainError("Asset.asset_number is required")
        if not name or not name.strip():
            raise AssetDomainError("Asset.name is required")
        if not asset_category_id:
            raise AssetDomainError("Asset.asset_category_id is required")
        if not operation_id:
            raise AssetDomainError("Asset.operation_id is required")
        return cls(
            id=new_uuid(), asset_number=asset_number.strip(), name=name.strip(),
            asset_category_id=asset_category_id, operation_id=operation_id,
            created_by_user_id=created_by_user_id,
            origin_branch_id=origin_branch_id,
            current_branch_id=current_branch_id or origin_branch_id,
            **extra,
        )

    def _assert_not_terminal(self) -> None:
        if self.status in _TERMINAL_STATUSES:
            raise AssetStateInvalidError(
                f"No se puede modificar un activo en estado terminal {self.status.value}")

    def commission(self, *, operational_start_date: date | None = None) -> None:
        if self.status is not AssetStatus.DRAFT:
            raise AssetStateInvalidError(
                f"Solo un activo en DRAFT puede comisionarse (estado actual: {self.status.value})")
        self.status = AssetStatus.AVAILABLE
        self.commissioned_at = _utcnow()
        self.operational_start_date = operational_start_date or date.today()
        self.updated_at = _utcnow()

    def suspend(self, reason: str = "") -> None:
        self._assert_not_terminal()
        if self.status not in _SUSPENDABLE_STATUSES:
            raise AssetStateInvalidError(
                f"No se puede suspender un activo en estado {self.status.value}")
        self.status = AssetStatus.OUT_OF_SERVICE
        if reason:
            self.notes = f"{self.notes}\n[SUSPEND] {reason}".strip()
        self.updated_at = _utcnow()

    def reactivate(self) -> None:
        if self.status is not AssetStatus.OUT_OF_SERVICE:
            raise AssetStateInvalidError(
                f"Solo un activo OUT_OF_SERVICE puede reactivarse (estado actual: {self.status.value})")
        self.status = AssetStatus.AVAILABLE
        self.updated_at = _utcnow()

    def change_condition(self, new_condition: AssetCondition) -> None:
        self._assert_not_terminal()
        self.condition = new_condition
        self.updated_at = _utcnow()

    def change_criticality(self, new_criticality: AssetCriticality) -> None:
        self._assert_not_terminal()
        self.criticality = new_criticality
        self.updated_at = _utcnow()

    def relocate(self, branch_id: str, location_id: str | None) -> None:
        self._assert_not_terminal()
        if not branch_id:
            raise AssetDomainError("Asset.relocate requires a branch_id")
        self.current_branch_id = branch_id
        self.current_location_id = location_id
        self.updated_at = _utcnow()

    def is_available_for_assignment(self) -> bool:
        return self.status is AssetStatus.AVAILABLE
