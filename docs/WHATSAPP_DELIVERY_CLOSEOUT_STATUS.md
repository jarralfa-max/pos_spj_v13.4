# WhatsApp → Delivery Refactor Closeout Status

Fecha: 2026-05-23

## Objetivo
Cerrar en una sola sesión el estado de avance por PR lógico y dejar trazabilidad explícita de qué quedó cubierto y qué falta para declarar 100% completo el prompt maestro.

## PR lógicos ejecutados en esta sesión

### PR1 — Contrato canónico + sucursal global
- ✅ Comando "cambiar sucursal / otra sucursal" en número global enruta a `SELECTING_BRANCH`.
- ✅ Tests de router para branch switch.
- ✅ Payloads de `POSNotifier` ahora incluyen alias canónicos EN (`sale_id`, `branch_id`, `customer_id`, `delivery_type`, `workflow_type`, `source_channel`) manteniendo compat legacy.

### PR2 — Flujos operativos (counter/delivery/scheduled)
- ✅ Guard de workflow programado: no permite `scheduled/programado -> preparacion` sin activación previa.
- ✅ Test explícito agregado.

### PR3 — Cotización aceptación/conversión
- ✅ En fallback sin orchestrator, `CotizacionFlow` emite `WHATSAPP_QUOTE_ACCEPTED` y `WHATSAPP_QUOTE_CONVERTED_TO_SALE`.
- ✅ Test agregado para el camino fallback.

### PR4 — Notificaciones ERP (contratos y dedupe)
Se agregaron contratos con dedupe+severity+texto UI español:
- ✅ `notify_quote_converted`
- ✅ `notify_order_cancelled`
- ✅ `notify_adjustment_required`
- ✅ `notify_adjustment_accepted`
- ✅ `notify_adjustment_rejected`
- ✅ `notify_advance_paid`
- ✅ `notify_order_ready_counter`
- ✅ `notify_order_ready_delivery`
- ✅ `notify_scheduled_order_due_soon`
- ✅ `notify_order_delayed`
- ✅ `notify_order_cancelled_by_customer`
- ✅ `notify_order_in_route`
- ✅ `notify_order_delivered`
- ✅ `notify_quote_created`
- ✅ `notify_quote_rejected`

## Estado de cierre por criterio maestro (resumen)
- Cubierto por implementación + tests: base de contrato canónico, dedupe de inbox, severidades, scheduled demand, branch-switch command, guards de workflow, y eventos canónicos clave.
- Pendiente de cierre 100% (requiere PR adicional): deep-link de click en notificación al pedido exacto en UI, y validación E2E operativa completa con entorno integrado ERP+WA (más allá de unit tests).

## Recomendación de último PR técnico
1. Conectar click de inbox a apertura de pedido exacto (sale_id/order_id) en `main_window`.
2. Test de integración UI de click-routing.
3. Smoke E2E manual documentado por flujo: mostrador, reparto, programado, cotización->venta, ajuste fuera de tolerancia.
