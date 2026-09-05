"""ASSET-15 — integration port contracts (structural checks only; concrete
adapters live in the owning modules and are wired in a later phase)."""

import pytest

from backend.domain.assets.events import ALL_ASSET_EVENTS
from backend.domain.assets.integration_ports import EmployeeRef, SupplierRef


class TestRefsAreImmutable:
    def test_supplier_ref_is_frozen(self):
        ref = SupplierRef(id="sup-1", name="Refrigeración del Bajío", active=True)
        with pytest.raises(AttributeError):
            ref.active = False

    def test_employee_ref_is_frozen(self):
        ref = EmployeeRef(id="emp-1", name="Juan Pérez", active=True)
        with pytest.raises(AttributeError):
            ref.name = "otro"


class TestEventCatalogCompleteness:
    """§87 — spot-check that every phase's canonical events made it into
    ALL_ASSET_EVENTS (not exhaustive, but catches an accidental typo/omission
    in any single phase's block)."""

    @pytest.mark.parametrize("event_name", [
        "ASSET_REGISTERED", "ASSET_COMMISSIONED",
        "ASSET_ASSIGNED", "ASSET_RETURNED", "ASSET_LOANED",
        "ASSET_TRANSFER_REQUESTED", "ASSET_TRANSFER_RECEIVED",
        "MAINTENANCE_WORK_ORDER_CREATED", "MAINTENANCE_COST_CONFIRMED",
        "ASSET_INSPECTION_COMPLETED", "ASSET_INSPECTION_FAILED",
        "ASSET_METER_READING_RECORDED",
        "ASSET_DOCUMENT_UPLOADED", "ASSET_WARRANTY_EXPIRING",
        "ASSET_CAPITALIZATION_PROPOSED", "ASSET_CAPITALIZATION_POSTED",
        "ASSET_PHYSICAL_INVENTORY_STARTED", "ASSET_DISCREPANCY_RESOLVED",
        "ASSET_DISPOSAL_REQUESTED", "ASSET_DISPOSED",
        "ASSET_TAG_ISSUED", "ASSET_TAG_REPLACED",
    ])
    def test_event_is_registered(self, event_name):
        assert event_name in ALL_ASSET_EVENTS
