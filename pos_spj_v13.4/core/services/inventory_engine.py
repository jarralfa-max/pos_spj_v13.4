# core/services/inventory_engine.py — SHIM LIMPIO v13.3
"""
Shim de compatibilidad backward.
El motor real está en core/services/inventory/unified_inventory_service.py.

NOTA: Este archivo reemplaza el shim corrupto que tenía 30+ líneas
redundantes de 'InventoryEngine = InventoryEngine' (merge artifact).
"""
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
