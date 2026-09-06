"""QueryService for canonical inventory UI/API read models.

Only get_stock/list_stock/list_movements remain: they are the sole
methods with any reachable caller (GestionarInventarioUC, GetInventoryStockUseCase).
Every other legacy raw-SQL method that used to live here (list_stock_rows,
list_availability_rows, get_operational_kpis, list_recent_movements,
list_feed_movements, list_product_history, get_last_movement_map, and their
aliases) had zero production callers — the live enterprise inventory UI
(frontend/desktop/modules/inventory/) reads exclusively through the canonical
query services in backend/application/inventory/queries/ — and were removed.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.inventory_repository import (
    InventoryMovementRecord,
    InventoryRepository,
    InventoryStockRecord,
)


class InventoryQueryService:
    """Read-only application service backed by canonical inventory tables."""

    def __init__(self, repository: InventoryRepository) -> None:
        self._repository = repository
        self._connection = repository.connection

    def get_stock(self, product_id: str, branch_id: str) -> InventoryStockRecord:
        return self._repository.get_stock(product_id=str(product_id), branch_id=str(branch_id))

    def list_stock(self, branch_id: str) -> list[InventoryStockRecord]:
        return self._repository.list_stock(branch_id=str(branch_id))

    def list_movements(
        self,
        product_id: str | None = None,
        branch_id: str | None = None,
    ) -> list[InventoryMovementRecord]:
        return self._repository.list_movements(product_id=product_id, branch_id=branch_id)
