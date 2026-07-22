"""INV-25 unit — inventory UI view models + navigation (pure, no Qt)."""

from backend.application.inventory.permissions import ALL_INVENTORY_PERMISSIONS
from frontend.desktop.modules.inventory.navigation import (
    INVENTORY_NAV,
    visible_entries,
)
from frontend.desktop.modules.inventory.view_models import (
    availability_table,
    replenishment_table,
    source_es,
    status_es,
    urgency_es,
    urgency_variant,
)


class TestLabels:
    def test_status_and_urgency_es(self):
        assert status_es("AVAILABLE") == "Disponible"
        assert status_es("PENDING_INSPECTION") == "Por inspección"
        assert urgency_es("STOCKOUT") == "Sin existencia"
        assert source_es("TRANSFER") == "Transferencia"
        assert urgency_variant("CRITICAL") == "danger"

    def test_unknown_code_falls_back(self):
        assert status_es("ZZZ") == "ZZZ"
        assert status_es(None) == "—"


class TestTables:
    def test_availability_table(self):
        vm = availability_table([
            {"product_id": "p1", "on_hand": "10", "reserved": "3", "available": "7"}])
        assert vm.total == 1 and vm.row_ids == ["p1"]
        assert vm.rows[0][0] == "p1" and vm.rows[0][3].startswith("7")

    def test_replenishment_table_localizes_source_and_urgency(self):
        vm = replenishment_table([
            {"id": "s1", "product_id": "p1", "current_available": "2",
             "suggested_quantity": "18", "source_type": "PURCHASE", "urgency": "CRITICAL"}])
        assert vm.rows[0][3] == "Compra" and vm.rows[0][4] == "Crítico"


class TestNavigation:
    def test_all_permissions_are_granular_inventory_codes(self):
        for entry in INVENTORY_NAV:
            assert entry.permission in ALL_INVENTORY_PERMISSIONS
            assert entry.title and entry.tooltip  # es-MX label + tooltip present

    def test_visible_entries_filters_by_permission(self):
        allowed = {"INVENTORY_VIEW"}
        vis = visible_entries(lambda code: code in allowed)
        assert all(e.permission == "INVENTORY_VIEW" for e in vis)
        assert len(vis) < len(INVENTORY_NAV)
