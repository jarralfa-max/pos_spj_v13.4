"""QueryService for canonical inventory UI/API read models."""

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

    def get_stock(self, product_id: int, branch_id: int) -> InventoryStockRecord:
        return self._repository.get_stock(product_id=int(product_id), branch_id=int(branch_id))

    def list_stock(self, branch_id: int) -> list[InventoryStockRecord]:
        return self._repository.list_stock(branch_id=int(branch_id))

    def list_movements(
        self,
        product_id: int | None = None,
        branch_id: int | None = None,
    ) -> list[InventoryMovementRecord]:
        return self._repository.list_movements(product_id=product_id, branch_id=branch_id)
