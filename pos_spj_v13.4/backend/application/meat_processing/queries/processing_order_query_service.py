"""ProcessingOrderQueryService (PROC-23). Read-only wrapper over
ProcessingOrderRepository for the Órdenes UI page — the read path never goes
through raw SQL or the UI layer directly (mirrors ProcessGenealogyQueryService,
PROC-18)."""

from __future__ import annotations

from typing import Any

from backend.domain.meat_processing.entities.processing_order import ProcessingOrder
from backend.domain.meat_processing.enums import ProcessingOrderStatus
from backend.infrastructure.db.repositories.meat_processing.processing_order_repository import (
    ProcessingOrderRepository,
)


class ProcessingOrderQueryService:
    def __init__(self, connection: Any) -> None:
        self._repo = ProcessingOrderRepository(connection)

    @classmethod
    def from_connection(cls, connection: Any) -> "ProcessingOrderQueryService":
        return cls(connection)

    def list_by_branch(self, branch_id: str, *,
                        status: ProcessingOrderStatus | None = None
                        ) -> list[ProcessingOrder]:
        return self._repo.list_by_branch(branch_id, status=status)

    def get(self, order_id: str) -> ProcessingOrder | None:
        return self._repo.get(order_id)
