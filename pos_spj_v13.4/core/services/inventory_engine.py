# core/services/inventory_engine.py — SHIM LIMPIO v13.3
"""
Shim de compatibilidad backward.
El motor real está en core/services/inventory/unified_inventory_service.py.

NOTA: Este archivo reemplaza el shim corrupto que tenía 30+ líneas
redundantes de 'InventoryEngine = InventoryEngine' (merge artifact).
"""
import logging as _log
_log.getLogger("spj.inventory_engine").warning(
    "DEPRECATED: inventory_engine shim. "
    "Import directly from core.services.inventory.unified_inventory_service."
)

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
