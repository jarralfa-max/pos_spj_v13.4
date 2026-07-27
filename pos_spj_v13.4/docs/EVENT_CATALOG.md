# Event Catalog — Delivery Canonical Events

Este catálogo enumera los eventos canónicos del bounded context Delivery. Los nombres legacy se mantienen solo por `LegacyDeliveryEventBridge` durante la migración.

## Convenciones

- Nombres canónicos: mayúsculas en inglés, prefijo `DELIVERY_` para eventos logísticos y `INVENTORY_` para solicitudes hacia inventario.
- Payloads: JSON serializable; nunca incluir `db`, conexiones SQLite, objetos PyQt ni clientes WhatsApp.
- Idempotencia: usar `operation_id` estable en eventos críticos.
- Persistencia confiable: eventos críticos se registran en `delivery_outbox_events`.
- EventBus en memoria: permitido para refrescos/UI/compatibilidad, no como única garantía de inventario o notificación crítica.

## Eventos Delivery

| Evento | Crítico | Emisor principal | Payload requerido | Idempotencia sugerida | Consumidores |
| --- | --- | --- | --- | --- | --- |
| `DELIVERY_ORDER_CREATED` | No | `CreateDeliveryOrderUseCase` | `order_id`, `folio`, `direccion`, `total`, `sucursal_id`, `usuario` | `delivery:{order_id}:created` | UI, bridge legacy, notificaciones internas. |
| `DELIVERY_ORDER_RESERVED` | Sí operacional | `CreateDeliveryOrderUseCase` | `order_id`, `operation_id`, `items`, `branch_id` | `delivery:{order_id}` | `DeliveryInventoryProjectionService`. |
| `DELIVERY_ORDER_PREPARING` | No | `ChangeDeliveryStatusUseCase` | `order_id`, `folio`, `usuario`, `sucursal_id` | `delivery:{order_id}:preparacion` | UI/badges/notificaciones internas. |
| `DELIVERY_DRIVER_ASSIGNED` | No | Futuro caso de uso asignación | `order_id`, `driver_id`, `driver_nombre`, `tiempo_estimado` | `delivery:{order_id}:driver:{driver_id}` | UI, PWA, tracking. |
| `DELIVERY_OUT_FOR_DELIVERY` | No/WA | `ChangeDeliveryStatusUseCase` | `order_id`, `driver_id`, `folio`, `cliente_tel` | `delivery:{order_id}:en_ruta` | WhatsApp, bridge legacy, UI. |
| `DELIVERY_ORDER_DELIVERED` | Sí | `ChangeDeliveryStatusUseCase` | `order_id`, `folio`, `driver_id`, `total`, `sucursal_id`, `responsable` | `delivery:{order_id}:entregado` | Inventario, finanzas/caja, bridge legacy. |
| `DELIVERY_ORDER_CANCELLED` | Sí | `ChangeDeliveryStatusUseCase` / cancel use case | `order_id`, `folio`, `usuario`, `motivo` | `delivery:{order_id}:cancelado` | Inventario release, ventas projection, UI. |
| `DELIVERY_ADJUSTMENT_APPROVAL_REQUIRED` | Sí | `AdjustDeliveryWeightUseCase` | `order_id`, `item_id`, `folio`, `cliente_tel`, `requested_qty`, `prepared_qty`, `new_subtotal` | `delivery:{order_id}:item:{item_id}:adjustment_required` | WhatsApp notifier, UI badges. |
| `DELIVERY_ITEM_WEIGHT_ADJUSTED` | No | `AdjustDeliveryWeightUseCase` | `order_id`, `item_id`, `requested_qty`, `prepared_qty`, `new_total` | `delivery:{order_id}:item:{item_id}:weight_adjusted` | Totales/UI/auditoría. |
| `DELIVERY_TOTAL_UPDATED` | No/operacional | `DeliveryTotalService` / adjustment use case | `order_id`, `old_total`, `new_total`, `folio`, `cliente_tel` | `delivery:{order_id}:total:{new_total}` | Sale projection, pagos, UI. |
| `DELIVERY_SCHEDULED_ORDER_ACTIVATED` | No | `ActivateScheduledOrderUseCase` | `order_id`, `workflow_type`, `usuario`, `sucursal_id` | `delivery:{order_id}:scheduled_activated` | UI, ventas projection, WhatsApp. |

## Eventos hacia inventario

| Evento | Crítico | Payload requerido | Idempotencia sugerida | Consumidores |
| --- | --- | --- | --- | --- |
| `INVENTORY_COMMIT_REQUIRED` | Sí | `order_id`, `operation_id`, `items`, `sucursal_id` | `delivery:{order_id}` y por item `delivery:{order_id}:item:{item_id}:commit` | `DeliveryInventoryProjectionService`. |
| `INVENTORY_RELEASE_REQUIRED` | Sí | `order_id`, `operation_id`, `reason` | `delivery:{order_id}` | `DeliveryInventoryProjectionService`, bridge legacy. |

## Eventos de notificación

| Evento | Crítico | Payload requerido | Idempotencia sugerida | Consumidores |
| --- | --- | --- | --- | --- |
| `CUSTOMER_NOTIFICATION_REQUESTED` | Sí | `order_id`, `canal`, `template`, `params`, `cliente_tel` | `delivery:{order_id}:notify:{template}` | `WhatsAppDeliveryNotifier` / notification handler. |

## Bridge legacy temporal

| Canónico | Legacy emitido | Política |
| --- | --- | --- |
| `DELIVERY_ORDER_CREATED` | `pedido_delivery_creado`, `pedido_whatsapp_recibido` | Mantener hasta migrar UI/handlers WhatsApp a canónico. |
| `DELIVERY_OUT_FOR_DELIVERY` | `pedido_en_ruta` | Mantener hasta migrar consumidores de ruta. |
| `DELIVERY_ORDER_DELIVERED` | `pedido_entregado` | Mantener hasta migrar consumidores de entrega/liquidación. |
| `INVENTORY_RELEASE_REQUIRED` | `stock_liberar_solicitado` | Mantener hasta migrar liberación legacy. |
| `CUSTOMER_NOTIFICATION_REQUESTED` | No traduce a `notificacion_whatsapp_enviada` | `notificacion_whatsapp_enviada` solo confirma envío directo legacy. |

## Estados relacionados

| Estado delivery | Evento típico de entrada | Evento crítico asociado |
| --- | --- | --- |
| `pendiente` | `DELIVERY_ORDER_CREATED` | `DELIVERY_ORDER_RESERVED` si hay items inventariables. |
| `preparacion` | `DELIVERY_ORDER_PREPARING` | Ninguno obligatorio. |
| `en_ruta` | `DELIVERY_OUT_FOR_DELIVERY` | `CUSTOMER_NOTIFICATION_REQUESTED` opcional/según canal. |
| `entregado` | `DELIVERY_ORDER_DELIVERED` | `INVENTORY_COMMIT_REQUIRED`. |
| `cancelado` | `DELIVERY_ORDER_CANCELLED` | `INVENTORY_RELEASE_REQUIRED`. |
| `programado` activado | `DELIVERY_SCHEDULED_ORDER_ACTIVATED` | Reserva/forecast según flujo. |

## Referencias

- Arquitectura delivery: `docs/architecture/DELIVERY_ARCHITECTURE.md`.
- Auditoría y fases: `docs/audits/DELIVERY_REFACTOR_AUDIT.md`.
- WhatsApp + Delivery legacy: `docs/EVENT_CATALOG_WHATSAPP_DELIVERY.md`.
