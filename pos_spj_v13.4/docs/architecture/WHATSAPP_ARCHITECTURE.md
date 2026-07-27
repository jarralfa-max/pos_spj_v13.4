# WHATSAPP_ARCHITECTURE.md — Arquitectura WhatsApp (estado actual)

Actualizado: 2026-05-28

## 1) Camino oficial vs legacy

- **Producción (oficial):** `whatsapp_service/` (FastAPI + router + flows + ERP bridge + sender).
- **Legacy/fallback (congelado):** `pos_spj_v13.4/core/services/whatsapp_service.py` y shims `services/whatsapp_service.py`, `integrations/whatsapp_service.py`.
- Regla: nuevas reglas de negocio deben implementarse en el microservicio oficial, no en legacy.

## 2) Diagrama de alto nivel

```text
Meta Cloud API
   │
   ▼
/webhook (whatsapp_service/webhook/whatsapp.py)
   │
   ▼
MessageRouter + pipeline (whatsapp_service/router/message_router.py)
   │
   ├─► IntentParser (parser/intent_parser.py)
   ├─► Flows (pedido/cotización/pago/registro/menu)
   └─► Conversation store (state/conversation.py)
          │
          ├─► Business idempotency (state/business_idempotency.py)
          ├─► ERPBridge facade (erp/bridge.py)
          │      ├─► ERP API (preferido en producción)
          │      └─► SQLite fallback (solo development/test)
          └─► WAEventEmitter (erp/events.py)

Salida de mensajes:
flows/router ─► messaging/sender.py ─► Meta Graph API
```

## 3) Entradas y salidas principales

### Entradas
- Webhook Meta: `whatsapp_service/webhook/whatsapp.py`.
- Webhook MercadoPago: `whatsapp_service/webhook/mercadopago.py`.
- Notificaciones internas ERP→WA: `whatsapp_service/router/notify_router.py`.

### Salidas
- Envío a Meta: `whatsapp_service/messaging/sender.py`.
- Escrituras de negocio ERP: `whatsapp_service/erp/bridge.py` (API-first; SQLite fallback restringido por ambiente).
- Eventos: `whatsapp_service/erp/events.py`.

## 4) Reglas de ambiente para escrituras ERP

Configuración en `whatsapp_service/config/settings.py`:
- `get_app_env()`
- `is_production()`
- `is_test()`

En `production`:
- Si `_use_api` es falso, `ERPBridge` bloquea write SQLite mediante `_assert_sqlite_write_allowed(...)`.
- Si falla un write por API, `ERPBridge` no cae a SQLite; eleva error con `_handle_api_write_failure(...)`.

En `development` y `test`:
- se permite fallback SQLite para compatibilidad local/CI.

## 5) Idempotencia

- Idempotencia de mensajes (webhook): evita reprocesar por `message_id`.
- Idempotencia de negocio (persistente): `wa_business_idempotency` en `whatsapp_service/state/business_idempotency.py`.
- API del servicio: `get`, `start`, `complete`, `fail`, `run_once`.
- Integración actual: confirmación de pedido, conversión de cotización y confirmación de pago webhook.

## 6) Normalización de teléfonos

Módulo central:
- `whatsapp_service/phone_number.py`
- shim de dominio: `whatsapp_service/domain/phone_number.py`

Funciones:
- `normalize_to_e164`
- `normalize_to_digits`
- `normalize_to_mx_local10`
- `possible_match_key`

Uso actual en sender/bridge/aprobaciones para reducir divergencias de formato.

## 7) Pedido/cotización/pago (responsabilidades)

- `PedidoFlow` conversa y delega confirmación al caso de uso `ConfirmWhatsAppOrderUseCase`.
- `ConfirmWhatsAppOrderUseCase` encapsula orquestación principal de confirmación de pedido y política de anticipo vigente.
- `CotizacionFlow` aplica idempotencia al convertir cotización.
- `webhook/mercadopago.py` aplica idempotencia para confirmación de pago.

## 8) Eventos: dominio/canal/legacy

Referencia detallada: `docs/events/WHATSAPP_EVENT_CATALOG.md`.

Criterio:
- **Dominio ERP:** impacto de negocio (venta, pago, delivery, OC, etc.).
- **Canal WhatsApp:** actividad conversacional/mensajería.
- **Legacy:** compatibilidad temporal; no eliminar aún consumidores existentes.

## 9) Variables críticas de producción

- `ERP_API_URL`
- `ERP_API_KEY`
- `WA_INTERNAL_API_KEY`
- `WA_APP_SECRET`
- `WA_VERIFY_TOKEN`
- `WA_PHONE_NUMBER_ID`
- `WA_ACCESS_TOKEN`

## 10) Deuda técnica vigente (TODO reales)

- Separación incremental en curso: lógica de pagos y delivery ya delegada a gateways (`PaymentGateway`, `DeliveryGateway`); continuar migración del resto para evitar crecimiento de la fachada.
- Completar cobertura de idempotencia para todas las acciones críticas pendientes (p. ej. delivery en todos los caminos conversacionales).
- Consolidar completamente router pipeline para disminuir complejidad residual de `MessageRouter`.
- Completar migración de consumidores a eventos de dominio para reducir duplicidad conceptual con legacy.
