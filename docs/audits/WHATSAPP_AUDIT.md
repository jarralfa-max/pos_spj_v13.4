# WHATSAPP_AUDIT.md — Auditoría Módulo WhatsApp
**SPJ POS v13.4 → ERP Transformation**
Fecha: 2026-05-20

---

## 1. MAPA DE ARCHIVOS

### POS Core (`pos_spj_v13.4/`)

| Archivo | Responsabilidad | Estado |
|---------|----------------|--------|
| `modulos/whatsapp_module.py` | UI PyQt5 — configuración, historial, métricas | ⚠️ Contenía SQL directo, ahora refactorizado |
| `core/services/whatsapp_service.py` | Servicio canónico v12: queue, workers, envío Meta/Twilio, Rasa | ✅ Mantener como backend |
| `core/services/whatsapp_admin_service.py` | **NUEVO** Fachada para módulo UI | ✅ Creado en refactor |
| `core/services/whatsapp_credential_service.py` | **NUEVO** Gestión segura de credenciales | ✅ Creado en refactor |
| `core/services/delivery_whatsapp_service.py` | Notificaciones delivery (estado, peso) | ✅ OK |
| `core/repositories/whatsapp_config_repository.py` | **NUEVO** Acceso a `whatsapp_numeros` + `configuraciones` | ✅ Creado |
| `core/repositories/whatsapp_history_repository.py` | **NUEVO** Historial seguro (sin SQL injection) | ✅ Creado |
| `core/repositories/whatsapp_metrics_repository.py` | **NUEVO** Métricas agregadas | ✅ Creado |
| `core/integrations/whatsapp_client.py` | Cliente REST → microservicio WA | ✅ Corregido (rutas + auth) |
| `core/use_cases/pedido_wa.py` | Use case: procesar pedido desde WA | ✅ OK |
| `notifications/whatsapp_channel.py` | Adapter canal notificaciones unificado | ✅ OK |
| `services/whatsapp_service.py` | **SHIM v12** → re-exporta desde core | ✅ Mantener (legacy) |
| `integrations/whatsapp_service.py` | **SHIM v12** → re-exporta desde core | ✅ Mantener (legacy) |

### Microservicio (`whatsapp_service/`)

| Archivo | Responsabilidad | Estado |
|---------|----------------|--------|
| `main.py` | FastAPI entry point, lifecycle | ✅ Corregido (ERP_ROOT path) |
| `config/settings.py` | Variables de entorno centralizadas | ✅ Corregido (WA_API_URL None-safe + INTERNAL_API_KEY) |
| `config/numbers.py` | Registro de números WA desde BD | ✅ OK |
| `config/schedules.py` | Servicio de scheduling | ✅ OK |
| `webhook/whatsapp.py` | GET verification + POST mensajes Meta | ✅ OK (usa hmac.compare_digest) |
| `webhook/mercadopago.py` | Webhook pagos MercadoPago | ✅ OK |
| `router/notify_router.py` | Endpoints notificaciones POS→WA | ✅ Corregido (auth X-Internal-Key) |
| `router/message_router.py` | Router principal de mensajes | ✅ OK |
| `router/number_router.py` | Routing por número telefónico | ✅ OK |
| `messaging/sender.py` | Envío via WhatsApp Cloud API | ✅ OK (maneja ValueError explícito) |
| `messaging/interactive.py` | Mensajes interactivos (botones, listas) | ✅ OK |
| `messaging/templates.py` | Templates pre-aprobados | ✅ OK |
| `erp/bridge.py` | Puente ERP ↔ WA (read/write, API+SQLite) | ⚠️ Ver sección FASE 5 |
| `erp/events.py` | EventBus integration | ✅ Corregido (json.dumps) |
| `erp/business_orchestrator.py` | Orquestación flujos complejos | ✅ OK |
| `models/message.py` | Modelos de mensajes | ✅ OK |
| `models/context.py` | Contexto conversacional | ✅ OK |
| `flows/*.py` | State machines (menu, pedido, cotizacion, etc.) | ✅ OK |
| `parser/*.py` | Intent parser + product matcher + LLM | ✅ OK |
| `state/conversation.py` | Persistencia conversaciones SQLite | ✅ OK |
| `middleware/rate_limiter.py` | Rate limiting | ✅ OK |
| `middleware/handoff.py` | Handoff a agente humano | ✅ OK |

### Migraciones DB

| Migración | Tablas creadas | Estado |
|-----------|---------------|--------|
| `036_whatsapp_rasa.py` | `whatsapp_queue`, `rasa_sessions`, `marketing_messages` | ✅ OK |
| `042_whatsapp_multicanal.py` | `whatsapp_numeros`, `v_whatsapp_config` | ✅ OK |
| `050_wa_integration.py` | `wa_event_log`, `wa_reminder_queue`, `ordenes_compra` | ✅ OK |

---

## 2. RESPONSABILIDADES ACTUALES

### Flujo completo de un pedido WhatsApp:

```
Meta Cloud API
    ↓
GET/POST /webhook  (whatsapp_service/webhook/whatsapp.py)
    ↓
RateLimiter → DeduplicaciónConversationStore → NumberRouter
    ↓
MessageRouter → IntentParser (reglas + Ollama/DeepSeek)
    ↓
Flow (PedidoFlow, CotizacionFlow, PagoFlow, etc.)
    ↓
ERPBridge (read: SQLite/API | write: API gateway preferente, SQLite fallback)
    ↓
WAEventEmitter → EventBus ERP + wa_event_log
    ↓
sender.send_message → Meta Cloud API → cliente WhatsApp
```

### Flujo de notificación ERP → WhatsApp:

```
ERP Core (ventas, delivery, etc.)
    ↓
WhatsAppClient (core/integrations/whatsapp_client.py)
    ↓ POST /api/notify/* con X-Internal-Key
notify_router.py
    ↓
messaging/sender.py → Meta Cloud API
```

---

## 3. DUPLICIDADES IDENTIFICADAS

| Duplicidad | Archivos | Riesgo | Resolución |
|-----------|---------|--------|------------|
| Cola de mensajes | `whatsapp_queue` (migration 036) vs `wa_message_queue` (core service) | ALTO | `whatsapp_queue` = legacy, `wa_message_queue` = activa. Ver FASE 7 |
| Historial mensajes | `bot_mensajes_log` vs `wa_message_queue` vs `pedidos_whatsapp` | MEDIO | Repository abstrae ambas — devuelve primera con datos |
| Envío Meta | `core/services/whatsapp_service.py::_send_meta` vs `whatsapp_service/messaging/sender.py` | ALTO | `core/services` = legacy offline-first queue; `sender.py` = microservicio oficial |
| Webhook handler | `core/services/whatsapp_service.py::WebhookHandler` vs `whatsapp_service/webhook/whatsapp.py` | MEDIO | El de core es para dev local; el del microservicio es el oficial |
| Verificación webhook | `core/services` (HTTP basic) vs `whatsapp_service` (FastAPI + hmac) | BAJO | El del microservicio usa hmac.compare_digest (más seguro) |

---

## 4. RUTAS HTTP

### Microservicio (puerto 8000):

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| GET | `/webhook` | Verificación Meta Cloud API | Verify token |
| POST | `/webhook` | Recepción mensajes entrantes | Ninguna (Meta firma opcionalmente) |
| POST | `/api/notify/pedido-listo` | Notificar pedido listo | X-Internal-Key |
| POST | `/api/notify/anticipo` | Notificar anticipo requerido | X-Internal-Key |
| POST | `/api/notify/cotizacion` | Notificar cotización lista | X-Internal-Key |
| POST | `/api/notify/send` | Enviar mensaje libre | X-Internal-Key |
| POST | `/webhook/mercadopago` | Webhook pagos MP | MP signature |
| GET | `/health` | Health check | Ninguna |
| GET | `/` | Info del servicio | Ninguna |

### WhatsAppClient (POS Core) → Microservicio:

| Método | Ruta usada | OK? |
|--------|-----------|-----|
| `notificar_pedido_listo` | `/api/notify/pedido-listo` | ✅ |
| `notificar_anticipo_requerido` | `/api/notify/anticipo` | ✅ |
| `notificar_cotizacion_lista` | `/api/notify/cotizacion` | ✅ |
| `enviar_mensaje` | `/api/notify/send` | ✅ Corregido (era `/api/send`) |
| `health_check` | `/health` | ✅ |

---

## 5. TABLAS USADAS

| Tabla | Producida por | Consumida por | Canónica? |
|-------|-------------|--------------|-----------|
| `whatsapp_numeros` | Migration 042 | Core service, Microservicio (NumberRegistry, sender) | ✅ SÍ |
| `whatsapp_queue` | Migration 036 | Core service (legacy queue) | ⚠️ Legacy |
| `wa_message_queue` | Core service | UI historial | ✅ Activa |
| `bot_mensajes_log` | Core service/Rasa | UI historial | ⚠️ Secundaria |
| `rasa_sessions` | Migration 036 | Rasa integration | ⚠️ Legacy |
| `marketing_messages` | Migration 036 | Core service (_render) | ✅ OK |
| `wa_event_log` | WAEventEmitter | Auditoría | ✅ OK |
| `wa_reminder_queue` | Migration 050 | ScheduleService | ✅ OK |
| `pedidos_whatsapp` | Flows via bridge | UI historial/métricas | ✅ OK |
| `ordenes_compra` | Bridge (auto OC) | Compras | ✅ OK |
| `configuraciones` | UI (wa_* keys) | Core service config | ✅ OK |

---

## 6. EVENTOS EMITIDOS

| Evento | Productor | Consumidor esperado | Prioridad |
|--------|---------|-------------------|-----------|
| `WA_PEDIDO_CREADO` | WAEventEmitter | ERP (inventario, cocina) | 80 |
| `WA_COTIZACION_CREADA` | WAEventEmitter | ERP (cotizaciones) | 50 |
| `WA_VENTA_CONFIRMADA` | WAEventEmitter | ERP (finanzas) | 80 |
| `WA_ANTICIPO_REQUERIDO` | WAEventEmitter | ERP (anticipos) | 80 |
| `WA_ANTICIPO_PAGADO` | WAEventEmitter | ERP (finanzas) | 80 |
| `WA_CLIENTE_REGISTRADO` | WAEventEmitter | ERP (CRM) | 30 |
| `WA_ALERTA_GENERADA` | WAEventEmitter | Alertas | 10 |
| `SALE_CREATED` | WAEventEmitter | ERP | 80 |
| `PAYMENT_RECEIVED` | WAEventEmitter | ERP finanzas | 80 |

---

## 7. RIESGOS IDENTIFICADOS Y ESTADO

| Riesgo | Severidad | Estado |
|--------|-----------|--------|
| SQL injection en historial UI (string interpolation) | CRÍTICO | ✅ CORREGIDO — ahora usa parámetros seguros |
| `_ensure_table` en QWidget (schema en UI) | ALTO | ✅ CORREGIDO — eliminado del widget |
| Tokens mostrados completos en logs | ALTO | ✅ CORREGIDO — _mask_token() |
| `WA_API_URL` con None cuando no hay phone_id | MEDIO | ✅ CORREGIDO |
| `ERP_ROOT` apuntaba a `spj_pos_v13.30` (no existe) | MEDIO | ✅ CORREGIDO |
| `notify_router` sin autenticación | ALTO | ✅ CORREGIDO — X-Internal-Key |
| `WhatsAppClient.enviar_mensaje` usaba `/api/send` (ruta incorrecta) | MEDIO | ✅ CORREGIDO |
| `events.py` serializaba con `str()` en lugar de `json.dumps()` | MEDIO | ✅ CORREGIDO |
| `.env.example` apuntaba a BD incorrecta | BAJO | ✅ CORREGIDO |
| Métodos webhook en UI sin widgets correspondientes | BAJO | ✅ CORREGIDO — tab webhook agregado |
| `wa_message_queue` y `whatsapp_queue` — tabla dual | MEDIO | ⚠️ TODO: unificar (ver FASE 7) |
| `crear_cotizacion_wa` en bridge escribe SQL directo (no usa use case) | MEDIO | ⚠️ TODO: crear use case cotización WA |
| `registrar_anticipo` en bridge escribe SQL directo | MEDIO | ⚠️ TODO: crear use case anticipo |
| `confirmar_pago_anticipo` en bridge escribe SQL directo | MEDIO | ⚠️ TODO: exponer via API use case |

---

## 8. TODOs TÉCNICOS (Trabajo Pendiente)

### FASE 7 — Unificación de colas (PENDIENTE)

- **TODO**: Crear migración que renombre/unifique `whatsapp_queue` → `wa_message_queue`
- **TODO**: Crear vista `v_wa_historial` que abstraiga las tres fuentes de historial
- **TODO**: Deprecar `bot_mensajes_log` con alias/vista

### FASE 5 — Gateway interfaces (PENDIENTE)

- **TODO**: `ERPBridge.crear_cotizacion_wa` → debe usar `CotizacionUseCase` cuando exista API REST
- **TODO**: `ERPBridge.registrar_anticipo` → debe usar `AnticipoUseCase`
- **TODO**: `ERPBridge.confirmar_pago_anticipo` → debe verificar contra use case de pagos
- **TODO**: Crear `CustomerGateway`, `OrderGateway`, `QuoteGateway`, `PaymentGateway` como interfaces formales

### Seguridad adicional (PENDIENTE)

- **TODO**: Validar firma HMAC-SHA256 de Meta en POST /webhook (X-Hub-Signature-256)
- **TODO**: Rate limiting por IP además de por número telefónico
- **TODO**: Cola de mensajes con retries para el microservicio (pendiente implementar)

---

## 9. CHECKLIST PRODUCCIÓN

- [ ] Credenciales Meta configuradas (`WA_ACCESS_TOKEN`, `WA_PHONE_NUMBER_ID`)
- [ ] Webhook Meta apunta a microservicio (puerto 8000, ruta `/webhook`)
- [ ] `WA_VERIFY_TOKEN` configurado y coincide con Meta dashboard
- [ ] `INTERNAL_API_KEY` configurado (para seguridad notify_router)
- [ ] Número(s) por sucursal registrados en `whatsapp_numeros`
- [ ] Microservicio health OK (`GET /health`)
- [ ] ERP puede enviar notificaciones (`WhatsAppClient.health_check()`)
- [ ] Eventos auditables en `wa_event_log`
- [ ] UI sin SQL directo ✅ (corregido)
- [ ] Tokens no expuestos en logs ✅ (corregido)
- [ ] `.env.example` con rutas correctas ✅ (corregido)
