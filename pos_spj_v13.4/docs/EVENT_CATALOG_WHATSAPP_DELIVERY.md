# Event Catalog — WhatsApp + Delivery

## WHATSAPP_ORDER_CREATED
- Emitter: WhatsApp orchestration service.
- Consumers: Delivery orchestration, branch notifications, analytics.
- Persistence: `wa_event_log` or `event_log`.
- Idempotency key: `whatsapp_order_created:{sale_id}`.

## WHATSAPP_SCHEDULED_ORDER_CREATED
- Emitter: WhatsApp orchestration service.
- Consumers: Forecast service, branch notifications.
- Persistence: `wa_event_log` or `event_log`.
- Idempotency key: `whatsapp_scheduled_order_created:{sale_id}`.

## WHATSAPP_QUOTE_CREATED / ACCEPTED / REJECTED / CONVERTED_TO_SALE
- Emitter: Quote flow service.
- Consumers: Sales conversion, branch notifications.
- Persistence: `event_log`.
- Idempotency key: `quote:{quote_id}:{state}`.

## DELIVERY_ORDER_CREATED / DELIVERY_ORDER_STATUS_CHANGED
- Emitter: Delivery service.
- Consumers: UI badge updater, notification service.
- Persistence: `event_log`.
- Idempotency key: `delivery_order:{order_id}:{status}`.

## DELIVERY_ADJUSTMENT_APPROVAL_REQUIRED / ACCEPTED / REJECTED
- Emitter: Delivery adjustment service.
- Consumers: WhatsApp customer comms, desktop notifications, total recalculation.
- Persistence: `event_log`.
- Idempotency key: `adjustment:{delivery_id}:{item_id}:{status}`.

## FORECAST_DEMAND_UPDATED
- Emitter: Scheduled demand service.
- Consumers: Forecast engine, procurement assist modules.
- Persistence: `event_log`.
- Idempotency key: `forecast_demand:{sale_id}:{product_id}:{scheduled_at}`.

## BRANCH_NOTIFICATION_CREATED
- Emitter: Desktop/branch notification service.
- Consumers: ERP UI inbox and badge counters.
- Persistence: `notification_inbox` (+ optional `event_log`).
- Idempotency key: `branch_notification:{dedupe_key}`.

## Delivery canonical vs legacy bridge (Fase 11)
- Canonical source events: `DELIVERY_ORDER_CREATED`, `DELIVERY_ORDER_PREPARING`, `DELIVERY_OUT_FOR_DELIVERY`, `DELIVERY_ORDER_DELIVERED`, `DELIVERY_ORDER_CANCELLED`, `DELIVERY_ORDER_RESERVED`, `INVENTORY_COMMIT_REQUIRED`, `INVENTORY_RELEASE_REQUIRED`, `CUSTOMER_NOTIFICATION_REQUESTED`.
- Temporary bridge: `LegacyDeliveryEventBridge` translates canonical events to legacy names only for old consumers.
- Legacy translations currently supported:
  - `DELIVERY_ORDER_CREATED` → `pedido_delivery_creado`, `pedido_whatsapp_recibido`.
  - `DELIVERY_OUT_FOR_DELIVERY` → `pedido_en_ruta`.
  - `DELIVERY_ORDER_DELIVERED` → `pedido_entregado`.
  - `INVENTORY_RELEASE_REQUIRED` → `stock_liberar_solicitado`.
- `notificacion_whatsapp_enviada` is not generated from `CUSTOMER_NOTIFICATION_REQUESTED`; it remains a legacy confirmation emitted only after direct notifier success in compatibility mode.
- Removal policy: migrate listeners to canonical events first, then remove bridge translations in a later cleanup phase.
