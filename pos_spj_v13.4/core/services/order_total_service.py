from __future__ import annotations

from core.delivery.application.delivery_total_service import DeliveryTotalService
from repositories.delivery_repository import DeliveryRepository


class OrderTotalService:
    """Compatibility shim for legacy imports.

    The canonical implementation lives in `DeliveryTotalService`. This shim is
    intentionally kept so existing UI/WhatsApp code can still import
    `core.services.order_total_service.OrderTotalService` during migration.
    """

    def __init__(self, db, repository: DeliveryRepository | None = None):
        self.db = db
        self.repository = repository or DeliveryRepository(db)
        self.delivery_total_service = DeliveryTotalService(self.repository)

    def recalculate_order_total(self, order_id: int, *, commit: bool = True) -> float:
        return self.delivery_total_service.recalculate_order_total(order_id, commit=commit)
