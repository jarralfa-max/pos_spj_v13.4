# Auditoría: carga de datos Delivery / Pedidos y Entregas

## Problema

El módulo rediseñado de Delivery abre, pero varias secciones pueden quedar vacías porque la UI quedó conectada a nombres de tablas/columnas que no siempre existen en el esquema real.

## Flujo actual de carga

1. `ModuloDelivery.cargar_pedidos()` consulta `DeliveryService.list_orders()`.
2. `DeliveryService.list_orders()` delega a `DeliveryRepository.list_orders()`.
3. La fuente principal es `delivery_orders`.
4. Los pedidos WhatsApp pueden existir primero en `ventas`, por lo que si no se importan a `delivery_orders`, la UI parece vacía.
5. KPIs, notificaciones, historial, conversación y detalle usan consultas auxiliares que no deben romper la lista principal.

## Hallazgos principales

### Lista principal

Fuente esperada: `delivery_orders`.

Riesgo: si los pedidos están en `ventas` y no fueron sincronizados, la lista queda vacía.

Corrección recomendada: sincronizar ventas WhatsApp pendientes hacia `delivery_orders` desde servicio/repositorio, no desde UI.

### Productos del detalle

La UI consulta `cantidad_preparada`, pero el repositorio usa `prepared_qty`.

Corrección recomendada: helper defensivo que use `COALESCE(prepared_qty, cantidad)` y fallback a `detalles_venta`.

### Historial

La UI consulta `delivery_status_events`, pero el repositorio escribe `delivery_order_history`.

Corrección recomendada: leer primero `delivery_order_history`; usar `delivery_status_events` solo como compatibilidad.

### Conversación WhatsApp

La UI consulta `whatsapp_messages`, pero el microservicio puede guardar conversación en otra BD.

Corrección recomendada: no romper si `whatsapp_messages` no existe. Mostrar fallback: “Sin conversación registrada en ERP”.

### KPIs

`OrderBadgeService` consultaba `notification_inbox` sin verificar existencia.

Corrección aplicada: `OrderBadgeService` ahora valida tablas/columnas y devuelve 0 si faltan.

### Repartidores

La UI usa `drivers`, `driver_locations` y cortes. Deben centralizarse en repositorio/servicio.

Corrección aplicada: se agregó `DriverRepository` y `DriverService` para encapsular acceso y reglas básicas.

## Riesgos

- `delivery.py` todavía contiene creación de tablas en `_init_tables()`.
- El archivo UI es muy grande y mezcla responsabilidades históricas.
- La sincronización desde `ventas` a `delivery_orders` debe completarse en servicio para evitar dependencia del timer.

## Plan recomendado

1. Mantener `delivery_orders` como fuente operativa principal.
2. Sincronizar ventas WhatsApp pendientes antes de pintar la UI.
3. Hacer helpers defensivos para detalle, historial y conversación.
4. Evitar que KPIs/notificaciones vacíen la pantalla.
5. Sacar gradualmente creación de tablas desde UI.
6. Usar `DriverService` para cargar/asignar repartidores.
