# Delivery / Pedidos y Entregas — Checklist E2E Manual

## Objetivo
Validar en entorno real (staging/producción controlada) que la carga y operación del módulo Delivery funcionan con esquemas legacy y nuevos sin romper flujo.

## Pre-check DB (SQLite)
1. Contar ventas WhatsApp pendientes:
   - `SELECT COUNT(*) FROM ventas WHERE lower(canal)='whatsapp' AND lower(estado) IN ('pendiente','pendiente_wa','en_preparacion','preparacion','en_ruta','programado');`
2. Contar delivery_orders:
   - `SELECT COUNT(*) FROM delivery_orders;`
3. Revisar columnas de delivery_items:
   - `PRAGMA table_info(delivery_items);`
4. Revisar notification_inbox:
   - `SELECT name FROM sqlite_master WHERE type='table' AND name='notification_inbox';`

## Flujo visual principal
1. Abrir módulo **Pedidos y Entregas**.
2. Confirmar que lista carga pedidos sin crash.
3. Verificar stats: `Pedidos activos` y `Total cargados`.
4. Cambiar entre tabs:
   - Todos
   - Mostrador
   - Reparto
   - Programados
   - Ajustes pendientes
   - Historial

## Empty states diagnósticos (Fase 12)
1. Sin pedidos reales:
   - Debe mostrar: “No hay pedidos para el filtro seleccionado.”
2. Con ventas WA pendientes y sin delivery_orders:
   - Debe mostrar: “Hay pedidos WhatsApp en ventas pendientes de importar. Pulsa Actualizar.”
3. Simular fallo microservicio WA:
   - Debe mostrar: “No se pudo consultar el microservicio WhatsApp. Se mostrarán pedidos ya importados.”

## Detalle de pedido (fallbacks)
1. Seleccionar pedido con items en `delivery_items`:
   - Ver requested/prepared qty correctamente.
2. Pedido sin `delivery_items` pero con `detalles_venta`:
   - Debe mostrar productos via fallback.
3. Historial:
   - Carga desde `delivery_order_history`; fallback a `delivery_status_events` si aplica.
4. Conversación WA:
   - Si no existe `whatsapp_messages`, no debe romper; mostrar fallback.

## KPIs/Notificaciones
1. Si no existe `notification_inbox`, módulo debe abrir sin errores.
2. KPIs deben seguir mostrando conteos degradados (0) sin bloquear lista.

## Validación de filtros combinados
1. Buscar por folio + flujo Reparto.
2. Flujo Mostrador con pedidos legacy (`workflow_type` vacío, `delivery_type=pickup/sucursal`).
3. Programados con ventana:
   - Hoy / Mañana / Esta semana / Próximos 30 días.
4. Activar fecha + ajustes pendientes y confirmar que no oculta pedidos fuera de criterio esperado.

## Criterio de salida
- No crashes.
- Lista principal siempre renderiza aunque fallen auxiliares.
- Tabs/filters no esconden pedidos válidos por `workflow_type` vacío.
- EmptyState explica causa probable y siguiente acción.
