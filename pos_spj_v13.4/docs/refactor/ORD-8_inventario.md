# ORD-8 — Inventario (reserva)

Fecha: 2026-08-30/31. Alcance: master prompt §23-24 (Disponibilidad, Reserva, Release).

## Qué se construyó

- `backend/infrastructure/integrations/orders_delivery_inventory_client.py` —
  `OrdersDeliveryInventoryClient`, mirror de `SalesInventoryClient` pero contra la
  Inventory MODERNA ya migrada (`CreateReservationUseCase`/`ReleaseReservationUseCase`/
  `InventoryAvailabilityQueryService`), no la legacy `StockReservationService` de float.
  `ReservationSource.CUSTOMER_ORDER` ya existía en `backend/domain/inventory/enums.py` —
  confirmado por lectura antes de usarlo, no asumido; Inventario ya anticipaba esta
  integración.
- `CustomerOrderLine.inventory_reservation_id` (columna nueva) + `set_reservation()`/
  `clear_reservation()`. `CustomerOrder.mark_reserved()`/`mark_reservation_failed()`.
- `ReserveOrderInventoryUseCase` — reserva CADA línea por separado (una reserva de
  Inventario es por producto); si una línea falla a mitad, compensa liberando las que ya
  tuvieron éxito antes de reportar el fallo (nunca deja reservas huérfanas). Emite
  `ORDER_RESERVED`/`ORDER_RESERVATION_FAILED` (ya existían en el catálogo desde ORD-2).
- `ReleaseOrderInventoryUseCase` — libera todas las líneas con reserva activa.
- Pedidos/Delivery NUNCA escribe `inventory_balances`/`inventory_reservations`
  directamente — todo pasa por `CreateReservationUseCase`/`ReleaseReservationUseCase` de
  Inventario (§23-24 cumplido literalmente, verificado por los propios tests: el balance
  de `inventory_balances.reserved_quantity` cambia solo a través del use case real).

## Decisiones

- **Reutiliza `ORDER_CONFIRM`/`ORDER_CANCEL`** — no se crea un permiso "reserva.*" nuevo;
  reservar es el efecto automático de confirmar (§17), no una acción de usuario final
  distinta (mismo criterio que ORD-6 con la activación de programados).
- **Asignación de lotes (FEFO) y Commit NO se construyeron en esta fase** — `Commit` (§50)
  requiere `final_quantity`/`final_weight`, que solo existen después del ajuste de peso
  (ORD-10, no construido todavía); construirlo ahora significaría comprometer contra
  `requested_quantity`, exactamente lo que el prompt maestro prohíbe una vez que hay
  ajuste. Documentado como pendiente explícito, no un descuido.
- **`branch_id` duplica como `warehouse_id`** — misma simplificación ya establecida por
  `SalesInventoryClient` en este repositorio.

## Bug real encontrado y corregido antes de cerrar la fase

`CustomerOrder.mark_reserved()` (añadido en esta misma fase) llamaba a
`OrderReservationRequiredPolicy.ensure_confirmed(...)` sin que esa clase estuviera
importada en `entities.py` — `NameError` en tiempo de ejecución, no detectado hasta correr
los tests de integración reales contra ambos esquemas (orders_delivery + inventory).
Corregido agregando el import faltante. Recordatorio de por qué las pruebas de integración
contra esquema real (no solo mocks) importan.

## Tests

7 tests de integración nuevos, contra SQLite real con AMBOS esquemas (orders_delivery +
inventory) en la misma conexión — reserva exitosa, stock insuficiente, sin balance,
denegación por permiso, evento en outbox, liberación exitosa, liberación sin reserva
(no-op). Suite acumulada ORD-1..8: **119/119 pasando**.

## Pendiente

- Asignación de lotes (FEFO) y Commit — bloqueados por ORD-10 (peso variable), como se
  documentó arriba.
- `InventoryAvailabilityQueryService.is_available()` está expuesto en el cliente pero
  ningún caso de uso lo llama todavía como validación previa a reservar (§23
  "Disponibilidad" como paso explícito antes de confirmar) — hoy la disponibilidad se
  descubre al intentar reservar, no antes. Pendiente para cuando exista un flujo de
  "verificar antes de confirmar" en la UI.
