"""INV-25 unit — inventory UI view models + navigation (pure, no Qt)."""

from backend.application.inventory.permissions import ALL_INVENTORY_PERMISSIONS
from frontend.desktop.modules.inventory.navigation import (
    INVENTORY_NAV,
    visible_entries,
)
from frontend.desktop.modules.inventory.view_models import (
    alert_severity_variant,
    availability_table,
    locations_table,
    severity_filter_code,
    replenishment_table,
    source_es,
    status_es,
    urgency_es,
    urgency_variant,
    warehouse_status_es,
    warehouse_type_es,
    warehouses_table,
)


class _Node:
    def __init__(self, id, code, name, level, status, children=()):
        self.id, self.code, self.name = id, code, name
        self.level, self.status, self.children = level, status, list(children)


class TestLabels:
    def test_status_and_urgency_es(self):
        assert status_es("AVAILABLE") == "Disponible"
        assert status_es("PENDING_INSPECTION") == "Por inspección"
        assert urgency_es("STOCKOUT") == "Sin existencia"

    def test_severity_filter_code_normalization(self):
        # es-MX, inglés, acentos y caso, todos normalizan al código canónico
        assert severity_filter_code("crítica") == "CRITICAL"
        assert severity_filter_code("critica") == "CRITICAL"
        assert severity_filter_code("CRITICAL") == "CRITICAL"
        assert severity_filter_code("advertencia") == "WARNING"
        assert severity_filter_code("info") == "INFO"
        assert severity_filter_code("informativa") == "INFO"
        # término vacío o no reconocido → None (sin filtro)
        assert severity_filter_code("") is None
        assert severity_filter_code("   ") is None
        assert severity_filter_code("xyz") is None

    def test_alert_severity_variant(self):
        assert alert_severity_variant("CRITICAL") == "danger"
        assert alert_severity_variant("WARNING") == "warning"
        assert alert_severity_variant("INFO") == "info"
        assert alert_severity_variant("???") == "neutral"
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


class TestWarehouseTables:
    def test_warehouses_table_localizes(self):
        vm = warehouses_table([
            {"id": "w1", "code": "WH1", "name": "Central",
             "warehouse_type": "CENTRAL", "status": "BLOCKED"}])
        assert vm.rows[0][2] == warehouse_type_es("CENTRAL") == "Central"
        assert vm.rows[0][3] == warehouse_status_es("BLOCKED") == "Bloqueado"

    def test_locations_table_indents_hierarchy(self):
        tree = [_Node("a", "A1", "Pasillo", 0, "ACTIVE",
                      children=[_Node("r", "R1", "Rack", 1, "ACTIVE")])]
        vm = locations_table(tree)
        assert vm.total == 2 and vm.row_ids == ["a", "r"]
        assert vm.rows[0][0] == "A1"           # root, no indent
        assert vm.rows[1][0].startswith("· ")  # child indented
        assert vm.rows[1][3] == "Activa"


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

    def test_sidebar_has_the_21_canonical_sections_in_order(self):
        # §54 Design System SPJ — navegación lateral canónica del inventario.
        expected = [
            "Resumen", "Existencias", "Disponibilidad", "Almacenes", "Ubicaciones",
            "Lotes", "Peso variable", "Cadena de frío", "Reservas", "Movimientos",
            "Transferencias", "Recepciones", "Reposición", "Conteos", "Ajustes",
            "Cuarentena", "Caducidades", "Trazabilidad", "Alertas", "Auditoría",
            "Configuración",
        ]
        assert [e.title for e in INVENTORY_NAV] == expected

    def test_sidebar_page_ids_are_unique(self):
        ids = [e.page_id for e in INVENTORY_NAV]
        assert len(ids) == len(set(ids))
