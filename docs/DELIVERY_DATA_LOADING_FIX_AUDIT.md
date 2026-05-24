# Delivery Data Loading Fix Audit

## Flujo actual de carga
1. `ModuloDelivery.__init__` crea servicios y UI.
2. Se agenda `QTimer.singleShot(0, _initial_sync_whatsapp_orders)` y luego `cargar_pedidos()`.
3. `cargar_pedidos()` pide pedidos al servicio/repo y renderiza lista+kanban.
4. KPIs/notificaciones/header se actualizan de forma auxiliar (safe wrappers).

## Secciones y consultas
- Lista/Kanban: `DeliveryService.list_orders()` -> `DeliveryRepository.list_orders()` (`delivery_orders` + join `drivers`).
- Productos detalle: prioridad `delivery_items`; fallback `venta_items` legacy.
- Historial detalle: prioridad `delivery_order_history`; fallback `delivery_status_events`.
- Conversación WA: `whatsapp_messages` si existe, fallback a `whatsapp_order_id`+notas.
- KPIs: `OrderBadgeService`.
- Notificaciones: `notification_inbox` con dedupe.

## Tablas/columnas esperadas
- `delivery_orders`, `delivery_items`, `delivery_order_history`, `drivers`, `driver_locations`, `delivery_driver_cuts`, `ventas`, `detalles_venta`/`venta_items`, `notification_inbox`, `whatsapp_messages`.

## Riesgos detectados
- Carga principal podía vaciarse por errores auxiliares.
- `_init_tables()` en UI creaba esquema de negocio (`delivery_orders`/`delivery_items`) conflictivo.
- Ausencia de tablas auxiliares (ej. `notification_inbox`) rompía KPIs si no se protegía.

## Plan aplicado
- Sync inicial WhatsApp antes de primer paint.
- Logging y wrappers seguros para cargas auxiliares.
- `OrderBadgeService` con `_table_exists`/`_columns` y degradación a 0.
- `_init_tables()` reducido a shim de compatibilidad (drivers/location/cuts), sin crear delivery_orders/items.
