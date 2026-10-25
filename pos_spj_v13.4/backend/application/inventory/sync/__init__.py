"""Lado receptor de la sincronización de Inventario (§59, INV-22).

El ENVÍO de la estación al servidor ya no vive aquí: lo hace el motor de
replicación único (`backend/application/sync/replication_outbox.py`, Slice 2),
que toma `inventory_outbox` como fuente. El despachador propio de INV-22 era
código muerto (sin transporte ni llamadores de producción) y se retiró.

El ingestor idempotente se conserva hasta que la bandeja de entrada central
(Slice 4) lo absorba.
"""

from backend.application.inventory.sync.event_ingestor import InventoryEventIngestor

__all__ = ["InventoryEventIngestor"]
