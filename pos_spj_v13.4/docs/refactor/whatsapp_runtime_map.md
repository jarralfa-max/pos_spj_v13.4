# Mapa de runtime — Canal WhatsApp (FASE CERO — Auditoría)

Cómo fluye un mensaje hoy, de punta a punta, con nombres de función/clase/archivo reales.
Todas las rutas relativas a la raíz del repo (`C:\Users\Diego Rodriguez\Downloads\pos_spj_v13.4\`).

---

## 0. Arranque del sistema — cuántos procesos WhatsApp quedan vivos

Cuando se abre el ERP desktop (`pos_spj_v13.4/main.py`), en orden:

1. `AppContainer(db_path=DB_PATH)` (`main.py:166`) construye, entre otras cosas:
   - `core/app_container.py:380-385` → `self.whatsapp_service = WhatsAppService(conn=self.db, feature_service=...)`
     y **arranca su worker de cola** (`self.whatsapp_service.start_worker()`), un `threading.Thread`
     daemon que hace polling sobre la tabla `whatsapp_queue` (`core/services/whatsapp_service.py:402-427`).
   - `core/app_container.py:397-401` → construye `self.whatsapp_webhook = WhatsAppWebhookServer(port=8767, whatsapp_svc=self.whatsapp_service)`
     (no lo arranca todavía, solo lo instancia).
   - `core/app_container.py:388-393` → `NotificationService(db=..., whatsapp_service=self.whatsapp_service, ...)` —
     el servicio de notificaciones del ERP queda cableado al `WhatsAppService` **legacy**, no al microservicio.
   - `core/app_container.py:695-700` → `BotPedidosWA._default_container = self` (referencia de clase, para que
     cualquier instancia de `services/bot_pedidos.py` pueda usar los casos de uso del contenedor).
2. `main.py:175-182` → `launch_microservice_async(app_root)` — lanza en un thread daemon
   `core/services/microservice_launcher.py:MicroserviceLauncher.try_start()`, que primero hace
   `GET http://localhost:8000/health`; si no responde, hace `subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host","0.0.0.0","--port","8000"], cwd=whatsapp_service/)`
   y espera hasta 30s a que `/health` responda. Este es el arranque del microservicio **oficial**.
3. `main.py:184-188` → `container.whatsapp_webhook.start()` — **arranca sin condición** (el único guard es
   `hasattr`, siempre verdadero) el `WhatsAppWebhookServer` legacy en el puerto **8767**
   (`core/services/whatsapp_service.py:517-524`, `HTTPServer` estándar de `http.server`, un thread daemon
   `serve_forever`).

Resultado: en un boot normal del desktop quedan **dos servidores HTTP escuchando webhooks de WhatsApp**
simultáneamente (FastAPI en :8000, `HTTPServer` legacy en :8767), más un tercer proceso opcional
(Rasa action server en :5055) que se invoca bajo demanda desde el legacy si Rasa está corriendo
aparte. Cuál de las dos URLs (8000 u 8767) está efectivamente registrada como webhook en Meta Business
Manager es una configuración externa al repo — **requiere verificación operativa**, fuera del alcance
de esta auditoría de código. Independientemente de esa configuración, ambos procesos están activos y
capaces de procesar solicitudes si el tráfico llega a ellos (red interna, proxy mal configurado, o un
cambio de configuración accidental en Meta).

---

## 1. Camino entrante — microservicio oficial (`whatsapp_service/`)

```
Meta Cloud API
  │  POST /webhook  (X-Hub-Signature-256 si WA_APP_SECRET seteado)
  ▼
whatsapp_service/webhook/whatsapp.py:receive_message()  (líneas 62-119)
  │  1. verify_signature() si WA_APP_SECRET (línea 68-72) — fail-open si no seteado
  │  2. RateLimiter.is_status_update() / is_group_message() — descarta (líneas 80-85)
  │  3. IncomingMessage.from_webhook(data) (whatsapp_service/models/message.py)
  │  4. _conversation_store.is_duplicate(msg.message_id) — dedupe (línea 93)
  │  5. _rate_limiter.is_allowed(msg.from_number) (línea 98)
  │  6. _conversation_store.log_message(...) → INSERT message_log (línea 103-106)
  │  7. numero_cfg = _number_router.route(msg)  (whatsapp_service/router/number_router.py)
  ▼
whatsapp_service/router/message_router.py:MessageRouter.route(msg, numero_cfg)  (línea 114)
  │  — no auditado línea a línea en esta fase (366 líneas); según FASE 7 de la
  │    auditoría previa (2026-05-28) corre un pipeline de middlewares:
  │    NotificationNumberGuard → AdjustmentResponseMiddleware → BranchSelectionMiddleware
  │    → CancelFlowMiddleware → CustomerIdentificationMiddleware → resolución de intent
  │    (whatsapp_service/parser/intent_parser.py, con soporte IA en whatsapp_service/ai/)
  │    → despacho al flow correspondiente según FlowState (whatsapp_service/models/context.py)
  ▼
whatsapp_service/flows/{pedido,cotizacion,pago,delivery,registro,sucursal,repetir,menu}_flow.py
  │  Ejemplo pedido: PedidoFlow._handle_confirmacion() (pedido_flow.py:252-351)
  │    → BusinessIdempotencyService.run_once(action_key, ..., _create_order)
  │    → ConfirmWhatsAppOrderUseCase.execute(...)  (application/confirm_order_use_case.py:50-89)
  │       → self.erp.crear_pedido_wa(...) → ERPBridge.order_gateway.create()
  │          → _crear_pedido_wa_impl()  (erp/bridge.py:423-527)
  │             — API-first: POST /api/v1/pedidos si ERP_API_URL+ERP_API_KEY configurados (línea 433-465)
  │             — fallback SQLite si no: INSERT INTO ventas + detalles_venta (línea 467-527)
  │       → orchestrator.procesar_pedido_wa(...) si hay BusinessOrchestrator (confirm_order_use_case.py:66-77)
  │          → business_orchestrator.py:189-268: verifica stock, genera OC automática si falta,
  │            calcula anticipo (erp.calcular_anticipo_rules), programa delivery, emite eventos
  │       — si NO hay orchestrator: _evaluate_advance_policy() local (confirm_order_use_case.py:91-141)
  ▼
whatsapp_service/erp/pos_notifier.py:POSNotifier.notify_new_whatsapp_order(...)  (bridge.py:529-591, "puente WA→ERP desktop")
  │  INSERT wa_event_log (esquema con bug, ver whatsapp_schema_consolidation.md) + INSERT notification_inbox
  ▼
whatsapp_service/messaging/sender.py:send_text/send_buttons(...)  → Meta Graph API
  │  1. _is_whatsapp_opted_out(phone) — gate de consentimiento CRM-31 (sender.py:125-169)
  │  2. _get_whatsapp_config(sucursal_id) — token/phone_id (3 niveles de fallback, sender.py:56-108)
  │  3. httpx.AsyncClient POST a graph.facebook.com
```

Todo el tramo `MessageRouter → Flow → UseCase → ERPBridge` corre **síncrono dentro del propio request
handler de FastAPI** (`async def receive_message`, sin cola de trabajo intermedia) — es decir, el
webhook de Meta espera a que termine toda la cadena de negocio (incluida la llamada HTTP/SQLite al
ERP y el envío de la respuesta a Meta) antes de devolver 200. No hay un outbox/cola de reintentos
para el tramo entrante; si `_message_router.route()` lanza excepción, se captura genéricamente
(`webhook/whatsapp.py:114-117`) y se responde `{"status":"ok"}` igual — Meta nunca reintenta ese
evento porque el webhook siempre devuelve 200, y el mensaje se pierde silenciosamente salvo por el
log de error.

---

## 2. Camino saliente — notificación ERP→cliente iniciada por eventos internos

Dos caminos distintos coexisten, dependiendo de qué parte del ERP dispara la notificación:

### 2a. Vía REST oficial (`core/integrations/whatsapp_client.py` → microservicio)

```
Evento de negocio del ERP (ej. pedido listo)
  ▼
core/integrations/whatsapp_client.py:WhatsAppClient.notificar_pedido_listo(...)  (líneas 166-170)
  │  resuelve X-Internal-Key (parámetro > configuraciones.wa_internal_api_key > env > .env) (líneas 91-112)
  ▼
POST http://localhost:8000/api/notify/pedido-listo  (X-Internal-Key header)
  ▼
whatsapp_service/router/notify_router.py:pedido_listo()  (líneas 88-95)
  │  _check_internal_key() — fail-open si la key no está configurada (líneas 39-44)
  ▼
whatsapp_service/messaging/sender.py:send_text(...) → Meta Graph API
```

Usado, entre otros, por `core/delivery/infrastructure/whatsapp_delivery_notifier.py` (vía
`core/integrations/whatsapp_client.py:enviar_mensaje`) y por `notifications/whatsapp_channel.py`
(vía `core/services/delivery_whatsapp_service.py`).

### 2b. Vía cola legacy (`core/services/whatsapp_service.py`)

```
core/app_container.py — NotificationService(whatsapp_service=self.whatsapp_service, ...)
  ▼
core/services/whatsapp_service.py:WhatsAppService.send_message(...)  (líneas 291-302)
  │  MessageQueue.enqueue(...) → INSERT INTO whatsapp_queue (id UUIDv7, ...)  (líneas 144-156)
  ▼
WhatsAppService._worker_loop()  (thread daemon, líneas 402-427)
  │  cada ciclo: MessageQueue.get_pending() → _send_api() → _send_meta()/_send_twilio()
  │  _send_meta(): urllib.request directo a graph.facebook.com/v18.0/... (líneas 436-448, versión de API
  │  hardcodeada "v18.0", distinta de la "v21.0" configurable del microservicio)
  │  backoff exponencial 60*2^intentos hasta 960s, 5 intentos, luego dead-letter (líneas 109-111, 166-202)
```

Este camino es el que efectivamente usa `core/app_container.py:920-1014` (`_check_escalacion_pedidos`,
`_check_recordatorios_ordenes`, corridos cada 60s por `scheduler_service`) para: notificar al gerente
si un pedido `pedidos_whatsapp` lleva más de N minutos sin atender, enviar respuesta automática al
cliente, y recordatorios de anticipo/entrega desde `AnticipoCotizacionService`. **Es tráfico de
producción real hoy**, no código muerto.

---

## 3. Camino entrante — pipeline legacy (`WhatsAppWebhookServer`, puerto 8767)

```
Meta Cloud API (si esta URL estuviera registrada) o cualquier POST directo a :8767
  ▼
core/services/whatsapp_service.py:WebhookHandler.do_POST()  (líneas 490-497)
  │  SIN verificación de firma HMAC — el único chequeo de autenticidad es el verify_token
  │  comparado en do_GET() (líneas 480-488, comparación == plana, no HMAC/compare_digest)
  ▼
WebhookHandler._proc(data)  (líneas 499-515)
  │  extrae from_number/texto del primer mensaje del payload
  ▼
WhatsAppService.forward_to_rasa(from_number, texto)  (líneas 353-365)
  │  POST http://localhost:5005/webhooks/rest/webhook  (Rasa action server, si está corriendo)
  │  — si falla: WhatsAppService.procesar_mensaje_local() (líneas 367-382, respuestas hardcodeadas simples)
  ▼
WhatsAppService.send_message(phone_number=from_num, message=resp)  → misma cola/worker de §2b
```

Este camino **no comparte estado** con `whatsapp_service/state/conversation.py` (el `ConversationStore`
del microservicio oficial): tiene su propio ciclo de vida de "sesión" implícito vía `bot_pedidos.py`
(no confirmado en detalle en esta fase) y su propio dedupe (o ausencia de él — no se encontró
verificación de `message_id` duplicado en `WebhookHandler._proc`, a diferencia del webhook oficial que
sí lo hace en `whatsapp_service/webhook/whatsapp.py:93`).

---

## 4. Camino de pago — MercadoPago

```
PagoFlow._generar_link_pago(ctx)  (whatsapp_service/flows/pago_flow.py:72-121)
  │  POST https://api.mercadopago.com/checkout/preferences
  │  unit_price = ctx.total_pedido()  (calculado localmente en el contexto de conversación, línea 96)
  │  external_reference = f"{venta_id}:{ctx.phone}"  (línea 85)
  ▼
Cliente paga en MercadoPago
  ▼
POST /webhook/mercadopago  (whatsapp_service/webhook/mercadopago.py:25-157)
  │  verify_mp_signature() si MP_WEBHOOK_SECRET seteado (líneas 34-40) — fail-open si no
  │  GET https://api.mercadopago.com/v1/payments/{payment_id}  (confirma con MP, líneas 69-72)
  │  si status == "approved":
  │    - resuelve venta_id buscando por teléfono con LIKE sobre external_reference (líneas 96-114,
  │      heurística, no garantiza unicidad si el cliente tiene >1 pedido "pendiente_wa" abierto)
  │    - BusinessIdempotencyService.run_once("confirm_payment:{venta_id}:{monto}", ..., _confirm_payment)
  │      → ERPBridge.confirmar_pago_anticipo(...)  (erp/bridge.py:897-934)
  │    - emite PAYMENT_RECEIVED y WA_ANTICIPO_PAGADO
  │    - notifications.customer.notificar_pago_recibido(...)
```

---

## 5. UI desktop — wiring confirmado

```
interfaz/main_window.py:157  → from modulos.whatsapp_module import ModuloWhatsApp  (shim, 5 líneas)
  → modulos/whatsapp/__init__.py  → re-exporta desde modulos/whatsapp/whatsapp_module.py
interfaz/main_window.py:677  → self._conectar("WHATSAPP", ModuloWhatsApp, "📱 Pedidos WhatsApp")
interfaz/menu_lateral.py:322 → botón "📱 Pedidos WhatsApp" (flag "whatsapp_integration_enabled", línea 388)
```

`ModuloWhatsApp` (7 tabs: Estado/Credenciales/Números/Políticas/Webhook/Historial/Diagnóstico) es
**la única UI de administración WhatsApp efectivamente montada en el menú lateral**. Consume
exclusivamente `WhatsAppAdminService`/`WhatsAppCredentialService` (sin SQL directo). Su tab
"Historial" y sus métricas leen — vía `WhatsAppHistoryRepository`/`WhatsAppMetricsRepository` — una
mezcla de tablas del pipeline legacy (`bot_mensajes_log`, `pedidos_whatsapp`) y, cuando existe, la
`conversations.db` del microservicio nuevo; por tanto la UI de administración hoy **no distingue**
para el operador si un mensaje/pedido vino del microservicio oficial o del pipeline legacy — ambos se
mezclan en la misma pantalla de "Historial".

No se localizó en esta fase la UI de "Pedidos WhatsApp" propiamente dicha (mostrador/pesaje) que
consumiría `PedidosWhatsappService` — la memoria de la sesión orquestadora no la listó y no se buscó
explícitamente; **requiere verificación** (candidato: algo tipo `VentanaPedidos` en `modulos/`, no
confirmado).

---

## 6. Resumen de puntos de entrada (inventario compacto)

| # | Entrada | Archivo:función | Protegida por firma/HMAC | Vivo en producción |
|---|---|---|---|---|
| 1 | Webhook Meta oficial | `whatsapp_service/webhook/whatsapp.py:receive_message` | Sí, si `WA_APP_SECRET` seteado (fail-open si no) | Sí |
| 2 | Webhook Meta legacy | `core/services/whatsapp_service.py:WebhookHandler.do_POST` | No — ninguna | Sí, arranca en cada boot del desktop |
| 3 | Webhook MercadoPago | `whatsapp_service/webhook/mercadopago.py:mp_notification` | Sí, si `MP_WEBHOOK_SECRET` seteado (fail-open si no) | Sí |
| 4 | REST notify (ERP→WA) | `whatsapp_service/router/notify_router.py` | X-Internal-Key plano, fail-open si no configurado | Sí |
| 5 | REST delivery (ERP→WA) | `whatsapp_service/router/delivery_router.py` | Ídem #4 | Sí |
| 6 | Rasa action server | `rasa/actions/actions.py` | N/A (proceso separado, invocado por #2) | Condicional — solo si alguien ejecuta `rasa run actions` |
| 7 | Cola legacy saliente | `core/services/whatsapp_service.py:MessageQueue` | N/A (no es entrada HTTP) | Sí — usada por `NotificationService` del ERP y por el scheduler de escalación de pedidos |
