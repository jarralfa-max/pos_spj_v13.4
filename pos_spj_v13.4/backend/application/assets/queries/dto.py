"""Read DTOs for the Assets/EAM bounded context (ASSET-14, §63).

The UI never receives a domain entity directly — only these frozen,
serialization-friendly shapes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from backend.domain.assets.enums import (
    AssetCondition,
    AssetCriticality,
    AssetDisposalReason,
    AssetDisposalRequestStatus,
    AssetStatus,
    AssetWarrantyStatus,
)


@dataclass(frozen=True, slots=True)
class AssetSummaryDTO:
    id: str
    asset_number: str
    name: str
    category_name: str | None
    branch_id: str | None
    location_name: str | None
    custodian_user_id: str | None
    status: AssetStatus
    condition: AssetCondition
    criticality: AssetCriticality


@dataclass(frozen=True, slots=True)
class AssetDetailDTO:
    asset: AssetSummaryDTO
    description: str
    manufacturer: str
    model: str
    serial_number: str | None
    has_active_assignment: bool


@dataclass(frozen=True, slots=True)
class AssetDashboardKPIsDTO:
    total_assets: int
    available: int
    in_maintenance: int
    out_of_service: int
    disposal_pending: int


@dataclass(frozen=True, slots=True)
class MaintenanceWorkOrderSummaryDTO:
    id: str
    work_order_number: str
    asset_id: str
    status: str
    priority: AssetCriticality
    scheduled_at: str | None


@dataclass(frozen=True, slots=True)
class WarrantyAlertDTO:
    id: str
    asset_id: str
    provider_id: str
    expires_at: date
    status: AssetWarrantyStatus


@dataclass(frozen=True, slots=True)
class DisposalRequestSummaryDTO:
    id: str
    asset_id: str
    reason: AssetDisposalReason
    status: AssetDisposalRequestStatus
    requested_by: str
