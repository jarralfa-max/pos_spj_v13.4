from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_CONTAINER = REPO_ROOT / "core" / "app_container.py"
INVENTORY_UI = REPO_ROOT / "modulos" / "inventario_local.py"


def test_app_container_uses_only_canonical_inventory_route():
    source = APP_CONTAINER.read_text(encoding="utf-8")

    assert "from repositories.inventory_repository import InventoryRepository" not in source
    assert "from core.services.inventory.unified_inventory_service import UnifiedInventoryService" not in source
    assert "UnifiedInventoryService(" not in source
    assert "from backend.infrastructure.db.repositories.inventory_repository import InventoryRepository" in source
    assert "from backend.application.services.inventory_application_service import InventoryApplicationService" in source
    assert "from backend.application.queries.inventory_query_service import InventoryQueryService" in source
    assert "self.inventory_repository = InventoryRepository(self.db)" in source
    assert "self.inventory_query_service = InventoryQueryService(repository=self.inventory_repository)" in source
    assert "self.inventory_application_service = InventoryApplicationService(" in source
    assert "self.inventory_service = self.inventory_application_service" in source
    assert "repository=InventoryRepository(self.db)" not in source


def test_inventory_ui_mutations_use_canonical_application_service():
    source = INVENTORY_UI.read_text(encoding="utf-8")

    assert "from repositories.inventory_repository import InventoryRepository" not in source
    assert "UnifiedInventoryService" not in source
    assert "GestionarInventarioUC" not in source
    assert "self._inventory_app = InventoryApplicationService(repository=self._inventory_repository)" in source
    assert "self._inventory_app.increase_stock(" in source
    assert "self._inventory_app.adjust_stock(" in source
    assert "SELECT nombre, existencia" not in source
    assert "productos.existencia" not in source
