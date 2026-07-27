# WHATSAPP_PHASE0_SAFETY_MAP.md

Fecha: 2026-05-28  
Alcance: **FASE 0 — mapa de seguridad sin modificar código de runtime**.

## 1) Mapa completo de archivos WhatsApp

### ERP/POS monolito (`pos_spj_v13.4/`)
- Legacy runtime: `core/services/whatsapp_service.py`
- Shims: `services/whatsapp_service.py`, `integrations/whatsapp_service.py`
- Cliente ERP→microservicio: `core/integrations/whatsapp_client.py`
- Canal notificaciones: `notifications/whatsapp_channel.py`
- Delivery WA: `core/services/delivery_whatsapp_service.py`
- UI administrativa WA: `modulos/whatsapp*`
- Tests WA (monolito): `tests/test_wa_*.py`
- Migraciones WA: `migrations/standalone/{036,042,050,081,086,087,090}_*.py`

### Microservicio oficial (`whatsapp_service/`)
- Entry point: `main.py`
- Config: `config/settings.py`, `config/numbers.py`, `config/schedules.py`
- Webhooks: `webhook/whatsapp.py`, `webhook/mercadopago.py`
- Sender: `messaging/sender.py`
- Router: `router/message_router.py`, `router/number_router.py`, `router/notify_router.py`, `router/delivery_router.py`
- Flows: `flows/*.py` (pedido/cotización/pago/registro/menu/delivery/sucursal)
- ERP integration: `erp/bridge.py`, `erp/business_orchestrator.py`, `erp/events.py`, `erp/pos_notifier.py`
- Estado/idempotencia de mensaje: `state/conversation.py`
- Parser: `parser/intent_parser.py`, `parser/product_matcher.py`
- Middleware: `middleware/rate_limiter.py`, `middleware/handoff.py`, `middleware/hmac_validator.py`
- Tests WA (microservicio): `whatsapp_service/tests/*.py`

## 2) Puntos de entrada

1. **Webhook oficial**: `whatsapp_service/webhook/whatsapp.py` (`GET/POST /webhook`).
2. **Webhook legacy**: clases `WhatsAppWebhookServer`/`WebhookHandler` en `core/services/whatsapp_service.py`.
3. **Sender oficial**: `whatsapp_service/messaging/sender.py` (`send_message`, `send_text`, etc.).
4. **Sender legacy**: `core/services/whatsapp_service.py` (cola `whatsapp_queue` + envío proveedor).
5. **Cliente ERP→microservicio**: `core/integrations/whatsapp_client.py` hacia rutas `/api/notify/*`.

## 3) Flujo de pedido por WhatsApp (actual)

1. Meta → `POST /webhook`.
2. `webhook/whatsapp.py` valida firma/token, ignora status/grupos, dedupe por `message_id`.
3. `router/message_router.py` carga contexto y resuelve intent.
4. `flows/pedido_flow.py` guía conversación (categoría→producto→cantidad→entrega→confirmación).
5. Confirmación llama `ERPBridge.crear_pedido_wa()` o `BusinessOrchestrator.confirmar_pedido_whatsapp()` según wiring.
6. Emite eventos (`WA_PEDIDO_CREADO`, posibles derivados) y responde al cliente.

## 4) Flujo de cotización

1. Router deriva a `flows/cotizacion_flow.py`.
2. Arma items en contexto, calcula total estimado en flow.
3. Confirma con `ERPBridge.crear_cotizacion_wa()` u orchestrator.
4. Para aceptación: `convertir_cotizacion_a_venta()`.
5. Emite eventos WA + quote/sale según camino.

## 5) Flujo de pago/anticipo

1. `flows/pago_flow.py` maneja método de pago/link.
2. Genera link MercadoPago con `external_reference`.
3. `webhook/mercadopago.py` (si aplica) confirma pago y registra anticipo vía bridge/orchestrator.
4. Emisión de `PAYMENT_RECEIVED`/`WA_ANTICIPO_PAGADO`.

## 6) Flujo de delivery

1. Pedido domicilio desde `PedidoFlow`.
2. `ERPBridge.programar_delivery()` y/o `flows/delivery_flow.py`.
3. `router/delivery_router.py` y notificaciones internas para seguimiento.

## 7) Flujo de notificaciones internas

- `router/notify_router.py` recibe ERP→WA con `X-Internal-Key`.
- `erp/pos_notifier.py` escribe `wa_event_log` + `notification_inbox` (dedupe por `dedupe_key`).
- `notifications/*.py` construyen mensajes operativos (staff/clientes/alertas).

## 8) Escrituras directas a SQLite desde WhatsApp

### Confirmadas en `whatsapp_service/erp/bridge.py`
- `INSERT clientes` (`create_cliente_minimo` fallback).
- `INSERT ventas` + `INSERT detalles_venta` (`crear_pedido_wa`).
- `UPDATE ventas` (`actualizar_estado_pedido`, `programar_delivery`, confirmaciones).
- `INSERT cotizaciones` + `cotizaciones_detalle`.
- `UPDATE cotizaciones` (conversión/rechazo).
- `INSERT anticipos` + `UPDATE anticipos` (`registrar_anticipo`, `confirmar_pago_anticipo`).
- `INSERT ordenes_compra` (`generar_orden_compra`).

### Otras escrituras WA
- `state/conversation.py`: `INSERT/UPDATE conversations`, `INSERT message_log`.
- `erp/events.py`, `erp/pos_notifier.py`, `router/delivery_router.py`, `erp/adjustment_approval.py`: `INSERT wa_event_log`.
- Legacy `core/services/whatsapp_service.py`: `whatsapp_queue` (`INSERT/UPDATE` retries/dead-letter).

## 9) Lecturas directas a SQLite desde WhatsApp

- `ERPBridge`: clientes, productos, categorías, sucursales, ventas, cotizaciones, reglas anticipo, stock, historial asociado.
- `ConversationStore`: contexto y dedupe de `message_log`.
- `BusinessOrchestrator`: lectura de toggles, cotización detalle, folios.
- Legacy service: configuraciones/cola/historial marketing.

## 10) Dónde se calcula negocio hoy

- **Precio unitario / subtotal estimado**: `flows/pedido_flow.py`, `flows/cotizacion_flow.py` (usa precio de producto directo).
- **Total**: `PedidoItem.subtotal`/sum en flows + `ERPBridge` recalcula en operaciones.
- **Anticipo**: reglas en `ERPBridge` + fallbacks/decisiones en `PedidoFlow`/`BusinessOrchestrator`.
- **Crédito**: `ERPBridge.get_credito_disponible` y reglas conexas.
- **Stock**: validación en `PedidoFlow` y `ERPBridge.check_stock`.
- **Delivery**: reglas/programación en `ERPBridge` + `BusinessOrchestrator`.

## 11) Dónde se emiten eventos

- `erp/events.py`: `WAEventEmitter.emit` (+persistencia `wa_event_log`).
- `flows/pedido_flow.py`, `cotizacion_flow.py`, `registro_flow.py`, `pago_flow.py`.
- `erp/business_orchestrator.py` (dominio + canal + legacy en paralelo).
- `erp/pos_notifier.py` (inserta eventos duplicados conceptualmente para POS).

## 12) Dónde sí existe idempotencia

- `webhook/whatsapp.py` + `state/conversation.py`: dedupe por `message_id` (tabla `message_log`).
- `erp/pos_notifier.py`: dedupe por `dedupe_key` en `notification_inbox`.

## 13) Dónde falta idempotencia

- Confirmación de pedido (acción de negocio) independiente de `message_id`.
- Conversión de cotización→venta.
- Registro/confirmación de anticipo/pago.
- Programación de delivery.
- Reintentos webhook/clicks con distinto `message_id` pero misma intención.

## 14) Riesgos por severidad

### Crítico
- Escrituras SQLite en producción desde `ERPBridge` en fallback.
- Idempotencia solo a nivel mensaje, no a nivel acción de negocio.

### Alto
- Duplicidad de eventos dominio/canal/legacy con posible doble efecto.
- `MessageRouter` con demasiada orquestación acoplada.
- `BusinessOrchestrator` y `ERPBridge` asumiendo reglas de negocio núcleo ERP.

### Medio
- Normalización de teléfonos dispersa (`sender`, `bridge`, legacy).
- Cálculo de total/anticipo en flows conversacionales.

### Bajo
- Deuda documental (nombres/ownership de eventos y caminos oficiales).

## 15) Tests existentes (resumen)

- Monolito: `pos_spj_v13.4/tests/test_wa_refactor.py`, `test_wa_flows.py`, `test_wa_bridge.py`, `test_wa_webhook.py`, `test_wa_client.py`, `test_wa_orchestrator.py`, `test_wa_parser.py`, `test_wa_repositories.py`.
- Microservicio: `whatsapp_service/tests/test_message_router_*.py`, `test_cotizacion_flow_phase6.py`, `test_pos_notifier_dedupe.py`, `test_bridge_notification_routing.py`, etc.

## 16) Tests faltantes (prioridad)

1. Producción: bloquear writes SQLite cuando API no está disponible.
2. Producción: falla API de write **no** cae a SQLite.
3. Idempotencia de negocio para pedido/cotización/pago/delivery.
4. Dedupe de misma acción con distinto `message_id`.
5. Normalización única de teléfonos (casos `+52`, `521`, `whatsapp:+52`, inválidos).
6. Evento único de dominio por acción crítica (sin duplicar efectos).
7. Cobertura webhook MP para pagos repetidos.

## Dependencias detectadas para siguientes fases

- **FASE 2** depende de centralizar ambiente (`development/test/production`) en `config/settings.py`.
- **FASE 3** depende de crear almacenamiento persistente de idempotencia de negocio (nueva tabla/migración).
- **FASE 5** depende de definir puertos/use case para sacar cálculo de negocio de `PedidoFlow`.

