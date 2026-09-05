"""ASSET-14 — QueryServices, exercised against fake in-memory repository ports.

These fakes satisfy the domain's Protocol repository ports structurally
(duck typing) — no infrastructure/persistence layer exists yet, but the
QueryServices are still fully testable because they depend on the
Protocol, not on a concrete SQLite implementation.
"""

from datetime import date, timedelta
from decimal import Decimal

from backend.application.assets.queries.asset_read_services import (
    AssetDashboardQueryService,
    AssetDetailQueryService,
    AssetDirectoryQueryService,
    AssetDisposalQueryService,
    AssetWarrantyQueryService,
    MaintenanceWorkOrderQueryService,
)
from backend.domain.assets.entities.asset import Asset
from backend.domain.assets.entities.asset_assignment import AssetAssignment
from backend.domain.assets.entities.asset_category import AssetCategory
from backend.domain.assets.entities.asset_disposal_request import AssetDisposalRequest
from backend.domain.assets.entities.asset_location import AssetLocation
from backend.domain.assets.entities.asset_warranty import AssetWarranty
from backend.domain.assets.entities.maintenance_work_order import MaintenanceWorkOrder
from backend.domain.assets.enums import (
    AssetAssignmentType,
    AssetDisposalReason,
    AssetLocationType,
    AssetStatus,
    MaintenanceType,
)
from backend.domain.finance.value_objects.money import Money


class _FakeAssetRepo:
    def __init__(self, assets):
        self._assets = {a.id: a for a in assets}

    def get(self, asset_id):
        return self._assets.get(asset_id)

    def list_by_branch(self, branch_id):
        return [a for a in self._assets.values() if a.current_branch_id == branch_id]

    def list_all(self):
        return list(self._assets.values())


class _FakeCategoryRepo:
    def __init__(self, categories):
        self._categories = {c.id: c for c in categories}

    def get(self, category_id):
        return self._categories.get(category_id)


class _FakeLocationRepo:
    def __init__(self, locations):
        self._locations = {l.id: l for l in locations}

    def get(self, location_id):
        return self._locations.get(location_id)


class _FakeAssignmentRepo:
    def __init__(self, assignments):
        self._assignments = assignments

    def get_active_for_asset(self, asset_id):
        for a in self._assignments:
            if a.asset_id == asset_id and a.is_active():
                return a
        return None


class _FakeWorkOrderRepo:
    def __init__(self, work_orders):
        self._work_orders = work_orders

    def list_open_for_asset(self, asset_id):
        return [wo for wo in self._work_orders if wo.asset_id == asset_id]

    def list_by_status(self, status):
        return [wo for wo in self._work_orders if wo.status.value == status]


class _FakeWarrantyRepo:
    def __init__(self, warranties):
        self._warranties = warranties

    def list_expiring(self, *, within_days=30):
        return [w for w in self._warranties if w.is_expiring(within_days=within_days)]


class _FakeDisposalRequestRepo:
    def __init__(self, requests):
        self._requests = requests

    def list_pending_review(self):
        from backend.domain.assets.enums import AssetDisposalRequestStatus
        return [r for r in self._requests if r.status in (
            AssetDisposalRequestStatus.REQUESTED, AssetDisposalRequestStatus.UNDER_REVIEW)]


def _asset(**extra) -> Asset:
    return Asset.create("ACT-000001", "Refrigerador", "cat-1", "op-1",
                        current_branch_id="br-1", **extra)


class TestAssetDirectoryQueryService:
    def test_list_by_branch_resolves_category_and_location(self):
        cat = AssetCategory.create("Refrigeración", "REF")
        loc = AssetLocation.create("br-1", "COC-1", "Cocina", AssetLocationType.AREA,
                                   parent_location_id="loc-branch")
        asset = Asset.create("ACT-000001", "Refrigerador", cat.id, "op-1",
                             current_branch_id="br-1", current_location_id=loc.id)
        svc = AssetDirectoryQueryService(_FakeAssetRepo([asset]), _FakeCategoryRepo([cat]),
                                         _FakeLocationRepo([loc]))
        results = svc.list_by_branch("br-1")
        assert len(results) == 1
        assert results[0].category_name == "Refrigeración"
        assert results[0].location_name == "Cocina"

    def test_list_by_branch_tolerates_missing_category(self):
        asset = _asset()
        svc = AssetDirectoryQueryService(_FakeAssetRepo([asset]), _FakeCategoryRepo([]),
                                         _FakeLocationRepo([]))
        results = svc.list_by_branch("br-1")
        assert results[0].category_name is None


class TestAssetDetailQueryService:
    def test_get_returns_none_for_unknown_asset(self):
        svc = AssetDetailQueryService(_FakeAssetRepo([]), _FakeCategoryRepo([]),
                                      _FakeLocationRepo([]), _FakeAssignmentRepo([]))
        assert svc.get("missing") is None

    def test_get_reports_active_assignment(self):
        asset = _asset()
        assignment = AssetAssignment.create(asset.id, AssetAssignmentType.CUSTODY, "br-1",
                                            "op-1", employee_id="emp-1")
        svc = AssetDetailQueryService(_FakeAssetRepo([asset]), _FakeCategoryRepo([]),
                                      _FakeLocationRepo([]), _FakeAssignmentRepo([assignment]))
        detail = svc.get(asset.id)
        assert detail.has_active_assignment is True


class TestAssetDashboardQueryService:
    def test_kpis_count_by_status(self):
        a1 = _asset()
        a1.commission()
        a2 = Asset.create("ACT-2", "x", "cat-1", "op-2", current_branch_id="br-1")
        a2.commission()
        a2.suspend()
        svc = AssetDashboardQueryService(_FakeAssetRepo([a1, a2]))
        kpis = svc.kpis(branch_id="br-1")
        assert kpis.total_assets == 2
        assert kpis.available == 1
        assert kpis.out_of_service == 1


class TestMaintenanceWorkOrderQueryService:
    def test_list_open_for_asset(self):
        wo = MaintenanceWorkOrder.create("WO-1", "asset-1", MaintenanceType.CORRECTIVE, "op-1")
        svc = MaintenanceWorkOrderQueryService(_FakeWorkOrderRepo([wo]))
        results = svc.list_open_for_asset("asset-1")
        assert len(results) == 1
        assert results[0].work_order_number == "WO-1"


class TestAssetWarrantyQueryService:
    def test_list_expiring(self):
        w = AssetWarranty.create("asset-1", "provider-1", "MANUFACTURER", date.today(),
                                 date.today() + timedelta(days=10), "op-1")
        svc = AssetWarrantyQueryService(_FakeWarrantyRepo([w]))
        results = svc.list_expiring(within_days=30)
        assert len(results) == 1
        assert results[0].asset_id == "asset-1"


class TestAssetDisposalQueryService:
    def test_list_pending_review(self):
        req = AssetDisposalRequest.create("asset-1", AssetDisposalReason.OBSOLESCENCE, "u1",
                                          "reemplazo", "op-1")
        svc = AssetDisposalQueryService(_FakeDisposalRequestRepo([req]))
        results = svc.list_pending_review()
        assert len(results) == 1
        assert results[0].reason is AssetDisposalReason.OBSOLESCENCE
