# core/services/inventory_engine.py — backward-compat shim
# Import directly from core.services.inventory.unified_inventory_service
from core.services.inventory.unified_inventory_service import (
    UnifiedInventoryService as InventoryEngine,
    UnifiedInventoryService,
    InventoryError,
    StockInsuficienteError,
)

__all__ = [
    "InventoryEngine",
    "UnifiedInventoryService",
    "InventoryError",
    "StockInsuficienteError",
]
