"""QueryServices for the Assets/EAM bounded context (ASSET-14, §63).

Depend only on the domain's Protocol repository ports (constructor
injection) — never on a concrete SQLite implementation. A future
infrastructure phase that builds real repositories automatically makes these
usable end-to-end; a real implementation of ``AssetRepositoryPort.
list_by_branch`` is also free to internally JOIN against categories/locations
for efficiency, the N+1 lookups here are an interim shape, not a contract.
Mirrors the bundled-file convention already used by
``backend/application/queries/finance/finance_read_services.py``.
"""

from __future__ import annotations

from backend.domain.assets.enums import AssetStatus
from backend.domain.assets.repository_ports import (
    AssetAssignmentRepositoryPort,
    AssetCategoryRepositoryPort,
    AssetDisposalRequestRepositoryPort,
    AssetLocationRepositoryPort,
    AssetRepositoryPort,
    AssetWarrantyRepositoryPort,
    MaintenanceWorkOrderRepositoryPort,
)
from backend.application.assets.queries.dto import (
    AssetDashboardKPIsDTO,
    AssetDetailDTO,
    AssetSummaryDTO,
    DisposalRequestSummaryDTO,
    MaintenanceWorkOrderSummaryDTO,
    WarrantyAlertDTO,
)

def _asset_to_summary(asset, categories: AssetCategoryRepositoryPort,
                       locations: AssetLocationRepositoryPort) -> AssetSummaryDTO:
    category = categories.get(asset.asset_category_id)
    location = locations.get(asset.current_location_id) if asset.current_location_id else None
    return AssetSummaryDTO(
        id=asset.id, asset_number=asset.asset_number, name=asset.name,
        category_name=category.name if category else None,
        branch_id=asset.current_branch_id,
        location_name=location.name if location else None,
        custodian_user_id=asset.custodian_user_id, status=asset.status,
        condition=asset.condition, criticality=asset.criticality,
    )


class AssetDirectoryQueryService:
    def __init__(self, assets: AssetRepositoryPort, categories: AssetCategoryRepositoryPort,
                 locations: AssetLocationRepositoryPort) -> None:
        self._assets = assets
        self._categories = categories
        self._locations = locations

    def list_by_branch(self, branch_id: str) -> list[AssetSummaryDTO]:
        return [_asset_to_summary(a, self._categories, self._locations)
                for a in self._assets.list_by_branch(branch_id)]

    def list_all(self) -> list[AssetSummaryDTO]:
        return [_asset_to_summary(a, self._categories, self._locations)
                for a in self._assets.list_all()]


class AssetDetailQueryService:
    def __init__(self, assets: AssetRepositoryPort, categories: AssetCategoryRepositoryPort,
                 locations: AssetLocationRepositoryPort,
                 assignments: AssetAssignmentRepositoryPort) -> None:
        self._assets = assets
        self._categories = categories
        self._locations = locations
        self._assignments = assignments

    def get(self, asset_id: str) -> AssetDetailDTO | None:
        asset = self._assets.get(asset_id)
        if asset is None:
            return None
        summary = _asset_to_summary(asset, self._categories, self._locations)
        active_assignment = self._assignments.get_active_for_asset(asset_id)
        return AssetDetailDTO(
            asset=summary, description=asset.description, manufacturer=asset.manufacturer,
            model=asset.model, serial_number=asset.serial_number,
            has_active_assignment=active_assignment is not None,
        )


class AssetDashboardQueryService:
    def __init__(self, assets: AssetRepositoryPort) -> None:
        self._assets = assets

    def kpis(self, *, branch_id: str | None = None) -> AssetDashboardKPIsDTO:
        items = self._assets.list_by_branch(branch_id) if branch_id else self._assets.list_all()
        return AssetDashboardKPIsDTO(
            total_assets=len(items),
            available=sum(1 for a in items if a.status is AssetStatus.AVAILABLE),
            in_maintenance=sum(1 for a in items if a.status is AssetStatus.IN_MAINTENANCE),
            out_of_service=sum(1 for a in items if a.status is AssetStatus.OUT_OF_SERVICE),
            disposal_pending=sum(1 for a in items if a.status is AssetStatus.DISPOSAL_PENDING),
        )


class MaintenanceWorkOrderQueryService:
    def __init__(self, work_orders: MaintenanceWorkOrderRepositoryPort) -> None:
        self._work_orders = work_orders

    def _to_summary(self, wo) -> MaintenanceWorkOrderSummaryDTO:
        return MaintenanceWorkOrderSummaryDTO(
            id=wo.id, work_order_number=wo.work_order_number, asset_id=wo.asset_id,
            status=wo.status.value, priority=wo.priority, scheduled_at=wo.scheduled_at,
        )

    def list_open_for_asset(self, asset_id: str) -> list[MaintenanceWorkOrderSummaryDTO]:
        return [self._to_summary(wo) for wo in self._work_orders.list_open_for_asset(asset_id)]

    def list_by_status(self, status: str) -> list[MaintenanceWorkOrderSummaryDTO]:
        return [self._to_summary(wo) for wo in self._work_orders.list_by_status(status)]

    def list_all_open(self, *, branch_id: str | None = None) -> list[MaintenanceWorkOrderSummaryDTO]:
        return [self._to_summary(wo) for wo in self._work_orders.list_all_open(branch_id=branch_id)]


class AssetWarrantyQueryService:
    def __init__(self, warranties: AssetWarrantyRepositoryPort) -> None:
        self._warranties = warranties

    def list_expiring(self, *, within_days: int = 30) -> list[WarrantyAlertDTO]:
        return [
            WarrantyAlertDTO(id=w.id, asset_id=w.asset_id, provider_id=w.provider_id,
                             expires_at=w.expires_at, status=w.status)
            for w in self._warranties.list_expiring(within_days=within_days)
        ]


class AssetDisposalQueryService:
    def __init__(self, requests: AssetDisposalRequestRepositoryPort) -> None:
        self._requests = requests

    def list_pending_review(self) -> list[DisposalRequestSummaryDTO]:
        return [
            DisposalRequestSummaryDTO(id=r.id, asset_id=r.asset_id, reason=r.reason,
                                      status=r.status, requested_by=r.requested_by)
            for r in self._requests.list_pending_review()
        ]
