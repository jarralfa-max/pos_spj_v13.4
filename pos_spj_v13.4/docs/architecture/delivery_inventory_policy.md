# Delivery-Inventory Integration Policy

## Policy A (Active)

- Sales module decrements inventory when a sale is confirmed (via `INVENTORY_COMMIT` event).
- Delivery validates availability and manages reservations only — it does NOT decrement stock itself.
- No double-decrement: inventory is only decremented once, by the sale handler.

## State transition rules

| Transition | Inventory action |
|---|---|
| pedido creado | No action (optional pre-check warning) |
| → preparacion | Stock availability check via `InventoryBalanceQueryService` (blocks if insufficient) |
| → en_ruta | No direct inventory action |
| → entregado | Publishes `INVENTORY_COMMIT_REQUIRED` (sale handler already decremented; reservation released) |
| → cancelado | Publishes `INVENTORY_RELEASE_REQUIRED` (releases any reservation) |

## Integration contract

- `ChangeDeliveryStatusUseCase` accepts optional `inventory_service` (duck-typed, must implement `get_product_balance(producto_id, sucursal_id)`).
- `DeliveryService` passes `self.inventory_service` to the use case.
- The canonical implementation is `backend.application.queries.inventory_balance_service.InventoryBalanceQueryService`.
- When `inventory_service` is `None`, the stock check is skipped (safe default for tests/legacy callers).

## What is NOT allowed

- `modulos/delivery.py` (UI) must never query `productos.existencia` or `inventario_actual` directly.
- `ChangeDeliveryStatusUseCase` must never contain raw SQL targeting inventory tables.
- Inventory stock must never be decremented by the delivery module — only by the sales module.

## Architecture guard tests

See `tests/architecture/test_delivery_arch.py` for automated enforcement of these rules.
