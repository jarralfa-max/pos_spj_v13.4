# WhatsApp/Delivery Refactor Audit

## Language mixing detected
- `delivery_service.py`, `delivery_repository.py` y `whatsapp_service/erp/bridge.py` mezclan claves como `cliente_tel`, `telefono`, `sucursal_id`, `estado`, `order_id`, `delivery_id`.
- Estados operativos en español (`pendiente`, `preparacion`, `en_ruta`, `entregado`) conviven con etiquetas/eventos en inglés (`DELIVERY_ORDER_CREATED`).

## Broken or fragile flow points
1. Ajustes de peso: hay lógica en service y más de una ruta de recálculo de totales.
2. Mapeo de payload WA no tiene contrato único para teléfono/nombre/branch.
3. Flujo programado no está normalizado con `workflow_type` canónico.
4. Conteo de pedidos en UI depende de rutas no completamente persistentes.

## Main participating tables
- `ventas`
- `detalle_ventas` (si aplica por módulo)
- `delivery_orders`
- `delivery_items`
- `delivery_order_history`
- `notification_inbox`
- `event_log` / `wa_event_log` (según despliegue)

## Existing event landscape (sample)
- `DELIVERY_ORDER_CREATED`
- `DELIVERY_ORDER_CANCELLED`
- `DELIVERY_ORDER_DELIVERED`
- `DELIVERY_OUT_FOR_DELIVERY`
- `INVENTORY_COMMIT_REQUIRED`
- Legacy events in Spanish (`pedido_en_ruta`, `pedido_entregado`)

## Missing canonical events
- `WHATSAPP_SCHEDULED_ORDER_CREATED`
- `WHATSAPP_QUOTE_ACCEPTED`
- `WHATSAPP_QUOTE_REJECTED`
- `WHATSAPP_QUOTE_CONVERTED_TO_SALE`
- `FORECAST_DEMAND_UPDATED`
- `BRANCH_NOTIFICATION_CREATED`
- `DELIVERY_ADJUSTMENT_APPROVAL_REQUIRED`
- `DELIVERY_ADJUSTMENT_ACCEPTED`
- `DELIVERY_ADJUSTMENT_REJECTED`

## Business rules that must be centralized
- Determinación de `workflow_type` (counter/delivery/scheduled).
- Normalización de estado (domain ↔ legacy ↔ UI).
- Reglas de ajuste de peso con tolerancia fija ±0.2 unidades.
- Recalculo único de total y sincronización `delivery_orders.total` ↔ `ventas.total`.
- Notificación por sucursal con dedupe key.

## Migration risks
- Duplicar columnas semánticamente equivalentes (ES + EN) sin mapper.
- Doble notificación por falta de idempotencia.
- Flujos divergentes entre microservicio y ERP desktop por eventos no persistidos.
- Romper legacy si UI sigue ejecutando SQL de transición.
