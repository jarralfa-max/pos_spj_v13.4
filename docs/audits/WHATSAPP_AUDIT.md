# WHATSAPP_AUDIT.md — Auditoría WhatsApp SPJ POS v13.4

Generado: 2026-05-20 | Fase 1 + actualización Fase 9

---

## 1. Mapa de archivos

### ERP POS (`pos_spj_v13.4/`)

| Archivo | Rol | Estado |
|---------|-----|--------|
| `modulos/whatsapp_module.py` | UI PyQt5 — admin WA | ✅ Refactorizado (solo UI) |
| `core/services/whatsapp_service.py` | Servicio unificado v12 (cola + Meta + Twilio) | ⚠️ Legacy — usar solo como fallback local |
| `core/services/whatsapp_admin_service.py` | **NEW** Facade admin WA | ✅ Nuevo |
| `core/services/whatsapp_credential_service.py` | **NEW** Gestión segura de credenciales | ✅ Nuevo |
| `core/repositories/whatsapp_config_repository.py` | **NEW** Datos config WA | ✅ Nuevo |
| `core/repositories/whatsapp_history_repository.py` | **NEW** Historial unificado sin SQL injection | ✅ Nuevo |
| `core/repositories/whatsapp_metrics_repository.py` | **NEW** Métricas WA | ✅ Nuevo |
| `core/integrations/whatsapp_client.py` | Cliente REST ERP → microservicio | ✅ Rutas corregidas + auth |
| `services/whatsapp_service.py` | SHIM v12 → core/services/ | ✅ Mantener |
| `integrations/whatsapp_service.py` | SHIM v12 → core/services/ | ✅ Mantener |
| `notifications/whatsapp_channel.py` | Canal de notificaciones | Sin cambios (no es UI) |
| `core/services/delivery_whatsapp_service.py` | Notificaciones delivery | Sin cambios |

### Microservicio (`whatsapp_service/`)

| Archivo | Rol | Estado |
|---------|-----|--------|
| `main.py` | FastAPI entry point | ✅ ERP_ROOT corregido |
| `config/settings.py` | Variables de entorno | ✅ WA_API_URL lazy / get_wa_api_url() |
| `config/numbers.py` | Registro números por sucursal | Sin cambios |
| `config/schedules.py` | Horarios | Sin cambios |
| `webhook/whatsapp.py` | GET/POST webhook Meta | Sin cambios (correcto) |
| `messaging/sender.py` | Envío via Graph API | ✅ Usa get_wa_api_url() |
| `router/notify_router.py` | REST ERP → WA notify | ✅ Auth X-Internal-Key agregada |
| `router/number_router.py` | Routing por número | Sin cambios |
| `router/message_router.py` | Routing de mensajes | Sin cambios |
| `erp/bridge.py` | Puente ERP ← → WA | ✅ Gateways + TODOs marcados |
| `erp/events.py` | EventBus integration | ✅ json.dumps, prioridad corregida |
| `erp/business_orchestrator.py` | Orquestador de negocio | Sin cambios |
| `flows/*.py` | Flujos conversacionales | Sin cambios |
| `parser/intent_parser.py` | NLP + parser | Sin cambios |
| `state/conversation.py` | Store de conversaciones | Sin cambios |
| `middleware/rate_limiter.py` | Rate limiting | Sin cambios |

### Migraciones

| Archivo | Tablas |
|---------|--------|
| `migrations/standalone/036_whatsapp_rasa.py` | `bot_sessions`, `bot_mensajes_log` |
| `migrations/standalone/042_whatsapp_multicanal.py` | `whatsapp_numeros` |
| `migrations/standalone/050_wa_integration.py` | `wa_message_queue`, `wa_event_log` |

---

## 2. Responsabilidades actuales

| Capa | Responsabilidad |
|------|----------------|
| `ModuloWhatsApp` (UI) | Solo presentación: tablas, formularios, botones |
| `WhatsAppAdminService` | Facade: orquesta repos, config, historial, métricas |
| `WhatsAppCredentialService` | Gestión segura de tokens Meta/Twilio |
| `WhatsAppConfigRepository` | CRUD `whatsapp_numeros` + `configuraciones` |
| `WhatsAppHistoryRepository` | Historial unificado (abstrae 3 tablas legacy) |
| `WhatsAppMetricsRepository` | Métricas de `pedidos_whatsapp` + `bot_sessions` |
| `core/services/whatsapp_service.py` | Cola offline-first + envío Meta/Twilio (legacy) |
| `WhatsAppClient` | REST client ERP → microservicio |
| Microservicio `notify_router` | Endpoints notify con auth interna |
| Microservicio `sender.py` | Envío real a Graph API Meta |
| `ERPBridge` | Acceso ERP (read+write) desde microservicio |

---

## 3. Duplicidades detectadas

| Duplicación | Descripción | Resolución |
|-------------|-------------|------------|
| **2 implementaciones de envío** | `core/services/whatsapp_service.py` + `messaging/sender.py` | Microservicio es el oficial. `WhatsAppService` queda como fallback legacy |
| **2 webhook servers** | `WhatsAppWebhookServer` (HTTPServer Python) + microservicio FastAPI | Microservicio es el oficial para producción |
| **3 tablas de historial** | `whatsapp_queue`, `wa_message_queue`, `bot_mensajes_log` | `WhatsAppHistoryRepository` abstrae todas |
| **3 shims whatsapp_service** | `services/`, `integrations/`, `core/services/` | Los 2 shims legacy apuntan a `core/` — conservar |

---

## 4. Rutas HTTP

### Microservicio (base: `http://localhost:8000`)

| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| GET | `/webhook` | Meta challenge | Verificación webhook Meta |
| POST | `/webhook` | Meta signature | Recepción mensajes WA |
| POST | `/api/notify/pedido-listo` | X-Internal-Key | Notificar pedido listo |
| POST | `/api/notify/anticipo` | X-Internal-Key | Notificar anticipo requerido |
| POST | `/api/notify/cotizacion` | X-Internal-Key | Notificar cotización lista |
| POST | `/api/notify/send` | X-Internal-Key | Envío libre |
| GET | `/health` | ninguna | Health check |
| POST | `/webhook/mercadopago` | MP signature | Webhook MercadoPago |

### ERP REST API (cuando configurado)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/v1/clientes?q=<phone>` | Buscar cliente |
| POST | `/api/v1/clientes` | Crear cliente |
| POST | `/api/v1/pedidos` | Crear pedido |
| PATCH | `/api/v1/pedidos/{id}/estado` | Actualizar estado |

---

## 5. Tablas usadas

| Tabla | Dueño | Accede |
|-------|-------|--------|
| `whatsapp_numeros` | ERP migrations 042 | UI, WhatsAppConfig, ERPBridge, NumberRegistry |
| `configuraciones` | ERP m000 | WhatsAppConfigRepository (prefijo `wa_`) |
| `wa_message_queue` | migrations 050 | WhatsAppHistoryRepository (lectura) |
| `whatsapp_queue` | WhatsAppService | MessageQueue (legacy) |
| `bot_mensajes_log` | migrations 036 | WhatsAppHistoryRepository (lectura) |
| `bot_sessions` | migrations 036 | WhatsAppMetricsRepository |
| `pedidos_whatsapp` | migrations 036/042 | Historial, métricas, bridge |
| `wa_event_log` | WAEventEmitter.ensure_tables() | WAEventEmitter |
| `ventas` | m000 | ERPBridge (write con TODO) |
| `detalles_venta` | m000 | ERPBridge (write con TODO) |
| `cotizaciones` | m000 | ERPBridge (write con TODO) |
| `anticipos` | m000 | ERPBridge (write con TODO) |
| `ordenes_compra` | m000 | ERPBridge (write con TODO) |

---

## 6. Eventos emitidos

Ver `docs/events/WHATSAPP_EVENT_CATALOG.md` para catálogo completo.

Eventos principales emitidos por `WAEventEmitter`:
- `WA_PEDIDO_CREADO` (prioridad 80)
- `WA_COTIZACION_CREADA` (prioridad 50)
- `WA_VENTA_CONFIRMADA` (prioridad 80)
- `WA_ANTICIPO_REQUERIDO` (prioridad 80)
- `WA_ANTICIPO_PAGADO` (prioridad 80)
- `WA_CLIENTE_REGISTRADO` (prioridad 30)
- `WA_ALERTA_GENERADA` (prioridad 10)

---

## 7. Riesgos y TODOs técnicos

### 🔴 Críticos (resueltos en esta fase)

| # | Riesgo | Resolución |
|---|--------|------------|
| R1 | SQL injection en `_cargar_historial` (concatenación directa) | ✅ `WhatsAppHistoryRepository` usa LIKE con parámetros |
| R2 | `WA_API_URL = None` en import time | ✅ `get_wa_api_url()` lazy |
| R3 | `WhatsAppClient.enviar_mensaje()` llamaba `/api/send` (ruta inexistente) | ✅ Corregido a `/api/notify/send` |
| R4 | `notify_router` sin autenticación | ✅ X-Internal-Key header |
| R5 | `_ensure_table()` en UI (viola regla 4) | ✅ Movido a `WhatsAppConfigRepository` |
| R6 | Estilos hardcodeados en UI (viola regla 6) | ✅ `spj_btn` + `apply_object_names` |
| R7 | `ERP_ROOT = "spj_pos_v13.30"` (path inexistente) | ✅ Corregido a `pos_spj_v13.4/pos_spj_v13.4` |
| R8 | `events.py` guardaba JSON como `str()` | ✅ Usa `json.dumps()` |
| R9 | Prioridad `≤ 2` para crítico (invertida vs spec) | ✅ Corregido a `≥ 80` |
| R10 | Métodos huérfanos (webhook) sin widgets | ✅ Tab Webhook agregado con widgets |

### ✅ TODOs resueltos

| # | Módulo | Estado |
|---|--------|--------|
| T1 | `ERPBridge.crear_cotizacion_wa()` | ✅ REST-first via `POST /api/v1/cotizaciones` + SQLite fallback |
| T2 | `ERPBridge.registrar_anticipo()` | ✅ REST-first via `POST /api/v1/anticipos` + SQLite fallback |
| T3 | `ERPBridge.confirmar_pago_anticipo()` | ✅ REST-first via `PATCH /api/v1/anticipos/{id}/confirmar` + SQLite fallback |
| T6 | ERP API Gateway | ✅ `/api/v1/cotizaciones`, `/api/v1/anticipos`, `/api/v1/ordenes-compra` implementados |
| T7 | Cola de mensajes con retries | ✅ Backoff exponencial `60 * 2^n` (máx 960s), dead-letter, migración 081 |

### ✅ Sin TODOs pendientes

Todos los métodos del `ERPBridge` tienen REST-first con fallback SQLite documentado.

---

## 8. Fallback SQLite (modo desarrollo)

Los siguientes métodos de `ERPBridge` escriben directamente a SQLite cuando
`ERP_API_URL` no está configurado. Esto está **permitido solo en desarrollo**.

En producción debe configurarse `ERP_API_URL + ERP_API_KEY` y los endpoints
REST del ERP deben existir para que las escrituras vayan por use cases.

Código marcado con `# TODO(FASE6): Fallback SQLite directo — modo desarrollo.`

### Cola de mensajes (migración 081)

`whatsapp_queue` tiene columna `proxima_revision` (TEXT ISO‑8601).
Backoff exponencial: `min(60 * 2^intentos, 960)` segundos.
Máx 5 reintentos → estado `fallido` (dead-letter).
Worker usa `seconds_until_next()` para sleep dinámico (0–300 s).
Índice: `idx_wa_queue_revision ON whatsapp_queue(estado, proxima_revision)`.

---

## 9. Checklist producción

- [ ] Meta: `WA_PHONE_NUMBER_ID` y `WA_ACCESS_TOKEN` configurados
- [ ] Webhook: URL pública registrada en Meta Business Manager
- [ ] `WA_VERIFY_TOKEN` configurado y coincide con Meta
- [ ] `WA_INTERNAL_API_KEY` generado (no vacío en producción)
- [ ] Número por sucursal registrado en `whatsapp_numeros`
- [ ] Microservicio health OK: `GET /health`
- [ ] ERP puede enviar notificaciones: `POST /api/notify/pedido-listo`
- [ ] Eventos auditables: tabla `wa_event_log` existe
- [ ] UI sin SQL directo: verificado
- [ ] Tokens no expuestos en logs: verificado
- [ ] `ERP_DB_PATH` apunta a DB correcta
- [ ] `ERP_API_URL` + `ERP_API_KEY` configurados (para writes por use cases)
