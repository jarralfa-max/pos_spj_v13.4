"""Use case for reading canonical inventory stock."""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.dto.use_case_result import UseCaseResult
from backend.application.queries.inventory_query_service import InventoryQueryService


@dataclass(frozen=True)
class GetInventoryStockCommand:
    operation_id: str
    product_id: str
    branch_id: str

    def validate_context(self) -> None:
        if not self.operation_id:
            raise ValueError("operation_id is required")
        if not str(self.product_id or "").strip():
            raise ValueError("product_id is required")
        if not str(self.branch_id or "").strip():
            raise ValueError("branch_id is required")


class GetInventoryStockUseCase:
    name = "GetInventoryStockUseCase"

    def __init__(self, query_service: InventoryQueryService) -> None:
        self._query_service = query_service

    def execute(self, command: GetInventoryStockCommand) -> UseCaseResult:
        command.validate_context()
        stock = self._query_service.get_stock(command.product_id, command.branch_id)
        return UseCaseResult(
            True,
            command.operation_id,
            entity_id=str(command.product_id),
            message="INVENTORY_STOCK_READ",
            data={
                "product_id": stock.product_id,
                "branch_id": stock.branch_id,
                "quantity": stock.quantity,
                "unit": stock.unit,
                "updated_at": stock.updated_at,
            },
        )
