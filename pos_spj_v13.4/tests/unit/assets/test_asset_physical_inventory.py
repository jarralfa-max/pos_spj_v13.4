"""ASSET-11 — AssetPhysicalInventory, AssetPhysicalInventoryLine, AssetPhysicalDiscrepancy."""

import pytest

from backend.domain.assets.entities.asset_physical_discrepancy import AssetPhysicalDiscrepancy
from backend.domain.assets.entities.asset_physical_inventory import AssetPhysicalInventory
from backend.domain.assets.entities.asset_physical_inventory_line import (
    AssetPhysicalInventoryLine,
)
from backend.domain.assets.enums import AssetDiscrepancyStatus, AssetPhysicalInventoryStatus, AssetScanResult
from backend.domain.assets.exceptions import (
    AssetDomainError,
    AssetPhysicalInventoryConflictError,
    SegregationOfDutiesError,
)


class TestAssetPhysicalInventory:
    def test_full_lifecycle(self):
        count = AssetPhysicalInventory.create("br-1", "auditor-1", "op-1")
        assert count.accepts_scans() is False
        count.start()
        assert count.accepts_scans() is True
        count.submit_for_review()
        count.complete()
        assert count.status is AssetPhysicalInventoryStatus.COMPLETED

    def test_cannot_scan_before_start(self):
        count = AssetPhysicalInventory.create("br-1", "auditor-1", "op-1")
        assert count.accepts_scans() is False

    def test_cannot_complete_before_review(self):
        count = AssetPhysicalInventory.create("br-1", "auditor-1", "op-1")
        count.start()
        with pytest.raises(AssetPhysicalInventoryConflictError):
            count.complete()

    def test_cancel_from_in_progress(self):
        count = AssetPhysicalInventory.create("br-1", "auditor-1", "op-1")
        count.start()
        count.cancel("conteo suspendido")
        assert count.status is AssetPhysicalInventoryStatus.CANCELLED

    def test_cancel_terminal_fails(self):
        count = AssetPhysicalInventory.create("br-1", "auditor-1", "op-1")
        count.start()
        count.submit_for_review()
        count.complete()
        with pytest.raises(AssetPhysicalInventoryConflictError):
            count.cancel()


class TestAssetPhysicalInventoryLine:
    def test_found_requires_asset_id(self):
        with pytest.raises(AssetDomainError):
            AssetPhysicalInventoryLine.create("count-1", "QR-001", AssetScanResult.FOUND,
                                              "scanner-1")

    def test_unregistered_does_not_require_asset_id(self):
        line = AssetPhysicalInventoryLine.create("count-1", "QR-999", AssetScanResult.UNREGISTERED,
                                                  "scanner-1")
        assert line.asset_id is None

    def test_is_clean(self):
        line = AssetPhysicalInventoryLine.create("count-1", "QR-001", AssetScanResult.FOUND,
                                                  "scanner-1", asset_id="asset-1")
        assert line.is_clean() is True


class TestAssetPhysicalDiscrepancy:
    def test_cannot_create_for_found_result(self):
        with pytest.raises(AssetDomainError):
            AssetPhysicalDiscrepancy.create("count-1", "asset-1", AssetScanResult.FOUND, "op-1")

    def test_full_workflow(self):
        d = AssetPhysicalDiscrepancy.create("count-1", "asset-1", AssetScanResult.MISSING, "op-1")
        d.begin_review()
        d.investigate()
        d.resolve("auditor-2", "Se localizó en otra sucursal")
        assert d.status is AssetDiscrepancyStatus.RESOLVED
        d.approve("supervisor-1")
        assert d.status is AssetDiscrepancyStatus.APPROVED

    def test_resolver_cannot_self_approve(self):
        d = AssetPhysicalDiscrepancy.create("count-1", "asset-1", AssetScanResult.MISSING, "op-1")
        d.begin_review()
        d.investigate()
        d.resolve("auditor-2", "Encontrado")
        with pytest.raises(SegregationOfDutiesError):
            d.approve("auditor-2")

    def test_resolve_requires_notes(self):
        d = AssetPhysicalDiscrepancy.create("count-1", "asset-1", AssetScanResult.DAMAGED, "op-1")
        d.begin_review()
        with pytest.raises(AssetDomainError):
            d.resolve("auditor-1", "")
