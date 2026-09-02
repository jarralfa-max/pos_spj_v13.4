"""OrdersDeliveryInventoryClient — Pedidos/Delivery's own integration point
onto Inventory (master prompt §23-24: "Inventario ejecuta la reserva.
Pedidos no escribe tablas de inventario."). Mirrors
`backend/infrastructure/integrations/sales_inventory_client.py`'s shape, but
wraps the MODERN, already-migrated Inventory reservation use cases
(`CreateReservationUseCase`/`ReleaseReservationUseCase`,
`InventoryAvailabilityQueryService`) rather than the legacy float-based
`StockReservationService` Sales uses — Inventory's own
`ReservationSource.CUSTOMER_ORDER`/`DELIVERY_ORDER` enum values exist
specifically for this integration (confirmed by reading
`backend/domain/inventory/enums.py` before choosing them, not assumed).

`branch_id` doubles as `warehouse_id` — same established simplification
`SalesInventoryClient` already uses for this codebase.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.inventory.queries.availability_query_service import (
    InventoryAvailabilityQueryService,
)
from backend.application.inventory.use_cases.reservation_use_cases import (
    CreateReservationUseCase,
    ReleaseReservationUseCase,
)
from backend.domain.inventory.enums import ReservationSource
from backend.domain.orders_delivery.exceptions import OrderInventoryReservationFailedError


class OrdersDeliveryInventoryClient:
    def __init__(self, connection, *, branch_id: str) -> None:
        self._connection = connection
        self._branch_id = branch_id
        self._availability = InventoryAvailabilityQueryService(connection)

    def is_available(self, *, product_id: str, quantity: Decimal) -> bool:
        return self._availability.is_available(
            product_id=product_id, branch_id=self._branch_id, quantity=quantity)

    def reserve_line(
        self, *, product_id: str, quantity: Decimal, weight: Decimal, order_id: str,
        operation_id: str, actor_user_id: str,
    ) -> str:
        """§23: reserves ONE order line's product/quantity. The caller
        (`ReserveOrderInventoryUseCase`) is responsible for compensating
        (releasing whatever already succeeded) if a later line fails —
        this client only ever reserves a single line per call."""
        result = CreateReservationUseCase().execute(
            self._connection, product_id=product_id, branch_id=self._branch_id,
            warehouse_id=self._branch_id, source=ReservationSource.CUSTOMER_ORDER,
            source_document_id=order_id, quantity=quantity, weight=weight,
            operation_id=operation_id, actor_user_id=actor_user_id)
        if not result.success:
            raise OrderInventoryReservationFailedError(result.message)
        return result.entity_id

    def release(self, reservation_id: str, *, operation_id: str, actor_user_id: str,
                reason: str = "") -> None:
        result = ReleaseReservationUseCase().execute(
            self._connection, reservation_id=reservation_id, operation_id=operation_id,
            actor_user_id=actor_user_id, reason=reason)
        if not result.success:
            raise OrderInventoryReservationFailedError(result.message)
