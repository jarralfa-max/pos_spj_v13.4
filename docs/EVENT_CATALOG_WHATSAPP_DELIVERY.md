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
