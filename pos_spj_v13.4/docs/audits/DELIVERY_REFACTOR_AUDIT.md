# Auditoría Fase 0 — Refactor Delivery/Pedidos/Entregas

## Archivos y dependencias actuales revisados

### Núcleo delivery
- `core/services/delivery_service.py`: fachada y lógica principal actual; crea pedidos, geocodifica, publica eventos, notifica WhatsApp, valida workflow, ajusta peso, sincroniza ventas, activa programados y sincroniza ventas WhatsApp pendientes.
- `repositories/delivery_repository.py`: persistencia SQLite de `delivery_orders`, `delivery_items`, `delivery_order_history`; históricamente también hacía migraciones defensivas y sincronizaba `ventas.estado`.
- `core/services/order_total_service.py`: recalcula total desde `delivery_items`, actualiza `delivery_orders.total` y también `ventas.total`.
- `core/services/reservation_service.py`: reservas, liberación y commit de inventario mediante `inventory_reservations`.
- `core/services/delivery_whatsapp_service.py`: mensajes/status WhatsApp delivery.
- `core/services/geocoding_service.py`: geocoding/autocomplete.
- `core/events/event_bus.py` y `core/events/handlers/delivery_handler.py`: EventBus en memoria y handlers de reserva, commit, WhatsApp, auditoría y liquidación.

### UI / módulos con acoplamiento delivery
- `modulos/delivery.py`: pantalla principal; usa `DeliveryService` pero también ejecuta SQL directo sobre `delivery_orders`, `delivery_items`, `drivers`, `delivery_status_events`/historial y WhatsApp. En Fase 13 se revisaron sus botones de acción: `TarjetaPedido`, el detalle/lista y `DeliveryActionPolicy` quedan alimentados por `DeliveryService.get_valid_actions()` / `DeliveryStateMachine` en vez de duplicar reglas de workflow.
- `integrations/delivery_pwa/pwa_server.py`: PWA de repartidores; antes fabricaba botones por strings legacy (`listo`, `en_camino`) y hacía `UPDATE delivery_orders` directo. En Fase 13 ahora expone acciones calculadas por backend y cambia estado vía `DeliveryService.update_status()`.
- `delivery/ticket_delivery.py`: ticket de delivery con consultas directas a `delivery_orders`, `delivery_items`, `drivers`.
- `delivery/asignacion_repartidor.py`: asignación de drivers con SQL directo sobre `drivers` y pedidos.
- `repositories/driver_repository.py` y `core/services/driver_service.py`: actualizan asignación/estado en delivery.

### Tests existentes relacionados
- `tests/test_delivery_service.py`, `tests/test_delivery_weight.py`, `tests/test_order_totals_phase8.py`, `tests/test_delivery_lifecycle.py`, `tests/test_delivery_action_policy.py`, `tests/test_delivery_repository_list_orders.py`, `tests/test_delivery_service_action_policy.py`, `tests/test_delivery_service_sync_sales.py`, `tests/test_delivery_ui_filters.py`, `tests/test_delivery_ticket_uses_escpos.py`.

## Tablas usadas

| Tabla | Uso actual | Riesgo |
| --- | --- | --- |
| `delivery_orders` | Estado logístico, cliente, dirección, venta vinculada, programados, total, JSON `historial_cambios`. | Mezcla fuente logística con compatibilidad legacy. |
| `delivery_items` | Items operativos, cantidades solicitadas/preparadas/finales, ajuste pendiente. | Duplica detalle comercial de `detalles_venta`. |
| `delivery_order_history` | Historial auditable parcial. | Convive con JSON `historial_cambios`. |
| `drivers` | Repartidores; usada por UI/repository/tickets. | Gestión mezclada con estado de pedido. |
| `ventas` | Venta comercial/fiscal, canal WhatsApp, estado comercial, total. | Actualizada desde repository, total service y service. |
| `detalles_venta` | Detalle comercial/fiscal. | Se copia hacia `delivery_items`. |
| `inventory_reservations` | Reserva offline-first de stock. | Eventos en memoria pueden perder commit/release. |
| `inventario_actual` | Stock físico calculado/cache. | No debe actualizarse directo desde delivery. |
| WhatsApp (`whatsapp_queue`, `wa_message_queue`, `pedidos_whatsapp`, `bot_sessions`, `bot_mensajes_log`, según instalación) | Ingreso/notificación WA. | Múltiples historiales/colas. |

## Eventos actuales encontrados

### Legacy publicados por delivery
- `pedido_delivery_creado`
- `pedido_whatsapp_recibido`
- `pedido_en_ruta`
- `pedido_entregado`
- `stock_liberar_solicitado`
- `notificacion_whatsapp_enviada`

### Canónicos/nuevos en uso parcial
- `DELIVERY_ORDER_CREATED`
- `DELIVERY_ORDER_RESERVED`
- `DELIVERY_ORDER_PREPARING`
- `DELIVERY_OUT_FOR_DELIVERY`
- `DELIVERY_ORDER_DELIVERED`
- `DELIVERY_ORDER_CANCELLED`
- `DELIVERY_ADJUSTMENT_APPROVAL_REQUIRED`
- `DELIVERY_ITEM_WEIGHT_ADJUSTED`
- `DELIVERY_TOTAL_UPDATED`
- `INVENTORY_COMMIT_REQUIRED`
- `CUSTOMER_NOTIFICATION_REQUESTED`
- `WHATSAPP_SCHEDULED_ORDER_ACTIVATED`

## Handlers suscritos / consumidores

- `core/events/handlers/delivery_handler.py` contiene handlers de reserva, liberación, ajuste de peso, pago, commit de inventario, notificación, auditoría, liquidación y sugerencias.
- `modulos/spj_refresh_mixin.py`, `ui/dashboard.py` y pantallas de módulos se suscriben a EventBus para refrescos.
- Algunos handlers aceptan `db` en payload como fallback; esto queda marcado como deuda porque rompe separación y transaccionalidad.

## Flujos actuales

### Crear pedido
1. `DeliveryService.create_order` valida dirección.
2. Geocodifica opcionalmente.
3. `DeliveryRepository.create_order` inserta `delivery_orders`, `delivery_items` e historial.
4. Publica eventos legacy y canónicos.
5. Solicita reserva con `DELIVERY_ORDER_RESERVED`.
6. Notifica WhatsApp directamente y publica `DELIVERY_ORDER_CREATED`.

### Cambiar estado
1. `DeliveryService.update_status` valida workflow con strings.
2. Bloquea `en_ruta`/`entregado` si hay ajuste pendiente.
3. `DeliveryRepository.update_status` actualiza `delivery_orders` y `ventas.estado`.
4. DeliveryService publica eventos, notifica WA y en entregado publica commit inventario.

### Ajuste de peso
1. `DeliveryService.adjust_item_weight` consulta item directo.
2. `ReservationService.compute_adjustment` decide tolerancia.
3. Dentro de tolerancia actualiza item y recalcula total.
4. Fuera de tolerancia guarda pending, bloquea pedido y notifica WA directo.

## Fuentes duplicadas de verdad

- Estado logístico: `delivery_orders.estado`, `ventas.estado`, UI hardcodeada.
- Items: `delivery_items` vs `detalles_venta`.
- Historial: `delivery_order_history` queda como fuente auditable; `delivery_orders.historial_cambios` se conserva temporalmente como compatibilidad deprecated.
- Total: `delivery_orders.total` es el total operativo recalculado desde `delivery_items`; `ventas.total` queda como proyección secundaria. Riesgo legacy: consumidores antiguos aún pueden escuchar `DELIVERY_TOTAL_UPDATED`.
- WhatsApp: `DeliveryWhatsAppService`, `WhatsAppClient` directo y colas/historiales WA.
- Inventario: reservas + eventos in-memory sin outbox transaccional.

## Riesgos detectados

1. Pedido entregado puede quedar sin commit de inventario si falla EventBus/handler.
2. `db` viaja en payloads, acoplando infraestructura a eventos.
3. Migraciones defensivas con `except Exception: pass` ocultan problemas de schema.
4. UI ejecuta SQL y puede saltarse reglas de dominio.
5. Venta puede recibir estados/totales divergentes desde varios puntos.
6. Ajustes pendientes bloquean estado en service, pero UI puede mostrar acciones por reglas propias.
7. Reintentos inexistentes en notificaciones críticas.

## Plan de migración por fases y archivos concretos

1. **Dominio**: crear `core/delivery/domain/{states,entities,events,state_machine,policies}.py` y tests `tests/test_delivery_state_machine.py`, `tests/test_delivery_weight_policy.py`.
2. **Schema**: crear `core/delivery/infrastructure/delivery_schema_migrator.py`, registrar `migrations/standalone/093_delivery_schema_migrator.py`, conservar `migrations/093_create_delivery_core.sql` como referencia SQL base y dejar `DeliveryRepository.ensure_schema` como shim deprecated. **Estado: implementado en Fase 2**.
3. **Fuente única/proyecciones**: crear `core/delivery/projections/sale_delivery_projection.py` para encapsular mapping `delivery_orders.estado` → `ventas.estado` y `delivery_orders.total` → `ventas.total` cuando aplique; `DeliveryRepository` ya no actualiza `ventas`. **Estado: implementado en Fase 3**.
4. **Use cases/application layer**: introducir `core/delivery/application/{create_delivery_order,change_delivery_status,adjust_delivery_weight,activate_scheduled_order,cancel_delivery_order,sync_whatsapp_orders}.py`; `DeliveryService` queda como fachada compatible que delega esos flujos. Los payloads emitidos desde estos casos de uso ya no transportan `db`. **Estado: implementado en Fase 4**.
5. **Outbox**: crear `core/delivery/infrastructure/delivery_outbox_repository.py` y `core/delivery/application/process_delivery_outbox.py`; registrar eventos críticos sin `db`, con `operation_id` para idempotencia y reintentos controlados. **Estado: implementado en Fase 5**.
6. **Inventario/reservas**: crear `InventoryReservationPort`, adapter `ReservationServiceInventoryAdapter` y `DeliveryInventoryProjectionService` para procesar reservas, liberaciones y commits desde eventos/outbox. El commit usa `final_qty`/`prepared_qty` cuando existen y `operation_id` por item para idempotencia. **Estado: implementado en Fase 6**.
7. **WhatsApp/notificaciones**: crear `DeliveryNotifierPort` y `WhatsAppDeliveryNotifier`, centralizar templates y enrutar `CUSTOMER_NOTIFICATION_REQUESTED` por outbox/notification handler en vez de llamadas WhatsApp directas desde casos de uso. **Estado: implementado en Fase 7**.
8. **Totales/pagos**: crear `core/delivery/application/delivery_total_service.py` como cálculo canónico desde `delivery_items`; mantener `OrderTotalService` como shim, proyectar `ventas.total` solo mediante `SaleDeliveryProjectionService` y registrar `DELIVERY_TOTAL_UPDATED` al aplicar/aceptar ajustes. **Estado: implementado en Fase 8**.
9. **Historial/auditoría**: ampliar `delivery_order_history` con `reason`, `metadata_json`, `event_id`, `usuario` y `created_at`; escribir toda transición de estado en la tabla auditable y conservar `historial_cambios` solo como JSON legacy deprecated. **Estado: implementado en Fase 9**.
10. **Compatibilidad DeliveryService**: mantener `DeliveryService` como fachada temporal con API legacy (`create_order`, `update_status`, `adjust_item_weight`, `list_orders`) y aliases explícitos (`create_delivery_order`, `update_order_status`, `adjust_weight`, `cancel_delivery_order`); marcar shims internos deprecated y delegar a use cases/outbox/proyecciones. **Estado: implementado en Fase 10**.
11. **Eventos legacy**: publicar eventos canónicos desde casos de uso y traducir temporalmente a legacy con `LegacyDeliveryEventBridge` (`pedido_delivery_creado`, `pedido_whatsapp_recibido`, `pedido_en_ruta`, `pedido_entregado`, `stock_liberar_solicitado`). `notificacion_whatsapp_enviada` queda solo para confirmaciones directas del notifier legacy. **Estado: implementado en Fase 11**.
12. **Tests obligatorios**: consolidar la matriz de creación, cambios de estado, inventario, ajustes, totales, outbox y compatibilidad en `tests/test_delivery_phase12_required.py`, cubriendo reglas críticas y deduplicación. **Estado: implementado en Fase 12**.
13. **UI**: migrar `modulos/delivery.py` progresivamente para pedir acciones a state machine/service y retirar SQL directo. En Fase 13 se completó el primer corte: `DeliveryService.get_valid_actions()` se apoya en `DeliveryStateMachine`, el fallback `DeliveryActionPolicy` usa la misma state machine y la PWA consulta acciones backend + cambia estado por la fachada. Quedan SQL directos de asignación, cobro, tickets y cortes por migrar en fases posteriores. **Estado: implementado parcialmente en Fase 13**.
14. **Documentación**: crear `docs/architecture/DELIVERY_ARCHITECTURE.md` con flujos, estados, eventos, fuentes de verdad, integraciones, outbox, compatibilidad y TODOs; crear/actualizar `docs/EVENT_CATALOG.md` con eventos canónicos delivery. **Estado: implementado en Fase 14**.
15. **Legacy bridge cleanup**: eliminar listeners legacy cuando consumidores migren a canónicos.

## Riesgos de compatibilidad

- Algunos handlers legacy aún tienen fallback para `payload["db"]`; los casos de uso de Fase 4/5/6/7 ya no lo envían y dependen del `db` inyectado en wiring/container.
- Durante la transición, los eventos canónicos pueden producir equivalentes legacy mediante `LegacyDeliveryEventBridge`; los consumidores deben ser idempotentes cuando el worker de outbox procese el mismo `operation_id`.
- El adapter de inventario de Fase 6 conserva `ReservationService` legacy detrás de un puerto; una fase posterior puede sustituirlo por el motor unificado sin tocar casos de uso delivery.
- `DeliveryService` sigue siendo la fachada temporal compatible; los aliases legacy y shims internos están documentados en `LEGACY_COMPATIBILITY_METHODS` y deben eliminarse solo cuando la UI/handlers hayan migrado.
- La fachada legacy `DeliveryWhatsAppService` sigue existiendo, pero ahora delega templates a `WhatsAppDeliveryNotifier`; las llamadas directas solo quedan como compatibilidad cuando no hay outbox inyectado.
- `DeliveryRepository.update_status` conserva compatibilidad, pero la proyección hacia ventas debe moverse en una fase posterior completa.
- La Fase 13 quitó la duplicación de reglas de acciones en `modulos/delivery.py` y PWA, pero aún quedan SQL directos UI para asignación/cobro/cortes/tickets que deben encapsularse antes de considerar la UI completamente limpia.
- Migraciones SQL son complementarias; en SQLite las columnas nuevas se agregan de forma segura por `DeliverySchemaMigrator`.
