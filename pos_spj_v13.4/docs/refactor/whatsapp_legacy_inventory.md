# Inventario legacy — Canal WhatsApp (FASE CERO — Auditoría)

Generado: 2026-09-01. Alcance: inventario archivo-por-archivo de todo lo relacionado con
WhatsApp en el repo, como insumo para el rediseño hacia bounded context
(`whatsapp_service/{domain,application,infrastructure,api,conversations}/whatsapp/...`)
descrito en el prompt maestro. **No se modificó ningún archivo de código** — este
documento y sus 5 acompañantes son el único artefacto de esta fase.

Convenciones de clasificación:
- **REUSE** — la lógica ya está en la forma correcta; solo cambia de paquete/import.
- **MOVE** — lógica correcta pero mal ubicada (capa equivocada); mover sin reescribir.
- **WRAP_TEMPORARILY** — mantener como shim de compatibilidad mientras se migra a lo nuevo.
- **REWRITE** — la lógica actual mezcla responsabilidades o está duplicada; reescribir contra el bounded context.
- **DELETE** — código muerto, no importado por ningún camino vivo.
- **BLOCKED** — no se puede decidir la clasificación final sin una decisión de producto/negocio.

Todas las rutas son relativas a `C:\Users\Diego Rodriguez\Downloads\pos_spj_v13.4\` (raíz del repo,
que contiene tanto `whatsapp_service/` como `pos_spj_v13.4/`, éste último con su propio `.git` anidado —
ver memoria `env_nested_git_repo_pos_spj`).

---

## 0. Hallazgo transversal: no hay UNO sino TRES pipelines de pedidos por WhatsApp vivos

Antes del inventario archivo por archivo, el hallazgo que condiciona toda la clasificación:
hoy conviven **tres implementaciones de "pedido por WhatsApp" simultáneamente activas**,
no solo "nuevo microservicio + legacy congelado":

1. **Oficial/nuevo** — `whatsapp_service/` (FastAPI). Escribe en `ventas` / `detalles_venta`
   vía `erp/bridge.py`. Arrancado automáticamente desde
   `pos_spj_v13.4/core/services/microservice_launcher.py:141-148`
   (`launch_microservice_async`, invocado en `pos_spj_v13.4/main.py:175-182` en cada boot del
   desktop).
2. **Legacy ERP-embebido** — `core/services/whatsapp_service.py` (`WhatsAppWebhookServer`,
   `HTTPServer` en puerto 8767) + `services/bot_pedidos.py` (893 líneas, máquina de estados
   conversacional completa para pedido/cotización) + `core/use_cases/pedido_wa.py` (228 líneas,
   escribe en `pedidos_whatsapp` / `pedidos_whatsapp_items`, **tablas distintas** a `ventas`).
   Instanciado y arrancado incondicionalmente en cada boot del desktop:
   `pos_spj_v13.4/core/app_container.py:380-401` (construcción) y
   `pos_spj_v13.4/main.py:184-188` (`container.whatsapp_webhook.start()`, sin flag de por medio —
   el único guard es `hasattr(container, "whatsapp_webhook")`, que siempre es `True`).
3. **Rasa** — `pos_spj_v13.4/rasa/actions/actions.py` (532 líneas, servidor de acciones Rasa SDK
   independiente, `rasa run actions --port 5055`, con su propia conexión SQLite
   (`DB_PATH = os.environ.get("SPJ_DB_PATH", "data/spj.db")` — **default distinto** a la ruta
   canónica `pos_spj_v13.4/data/spj_pos_database.db`). Invocado opcionalmente desde
   `core/services/whatsapp_service.py:353-365` (`forward_to_rasa`, POST a
   `http://localhost:5005/webhooks/rest/webhook`).

`services/bot_pedidos.py` está activamente conectado al contenedor de la app
(`BotPedidosWA._default_container = self` en `core/app_container.py:695-700`), no es código muerto.
No se trazó en esta fase si Meta Business Manager tiene registrada la URL del microservicio (8000)
o de este webhook legacy (8767) como webhook oficial — **requiere verificación operativa** (fuera
del alcance de una auditoría de código). Independientemente de cuál esté registrado en Meta, el
código legacy está compilado, wireado y listo para procesar tráfico si algo apunta a él.

Esto es la brecha arquitectónica más grande encontrada (ver también
`whatsapp_runtime_map.md` §0 y el resumen final).

---

## 1. `whatsapp_service/` — microservicio oficial

| Archivo | Rol | Capa actual | Líneas | Clasificación | Destino objetivo | Notas |
|---|---|---|---|---|---|---|
| `main.py` | Entry point FastAPI; construye TODO inline en `lifespan()` (migraciones, ERPBridge, WAEventEmitter, ConversationStore, ProductMatcher, OllamaClient, IntentParser, NumberRegistry, ScheduleService, HandoffService, routers) + hack de `sys.path` (líneas 38-52) | mixed | 188 | REWRITE | `api/whatsapp/main.py` (mínimo) + `infrastructure/whatsapp/bootstrap/application_factory.py` | El prompt maestro pide `main.py` mínimo (solo creación de app + `ApplicationFactory`). Hoy hace construcción manual de ~10 dependencias y ejecuta migraciones del ERP en el arranque del microservicio (líneas 76-84) — mezcla infraestructura de otro bounded context. |
| `ai/audit_log.py` | Log de decisiones de IA (intents resueltos) | infra | 52 | MOVE | `infrastructure/whatsapp/ai/audit_log.py` | No revisado en detalle línea por línea. |
| `ai/catalog_entity_extractor.py` | Extracción de productos/cantidades vía IA | infra | 211 | MOVE | `infrastructure/whatsapp/ai/` | No revisado en detalle. |
| `ai/fallback.py` | Mapeo de fallback cuando IA no disponible | infra | 38 | MOVE | `infrastructure/whatsapp/ai/` | — |
| `ai/intent_ai_client.py` | Cliente/config/timeout IA | infra | 67 | MOVE | `infrastructure/whatsapp/ai/` | — |
| `ai/intent_resolver.py` | Combina parser basado en reglas + IA | application | 146 | MOVE | `application/whatsapp/services/` | — |
| `ai/intent_schema.py` | Esquema de intents para IA | domain | 72 | MOVE | `domain/whatsapp/value_objects/` (si es forma pura) | Requiere verificación: si depende de librerías externas no es dominio puro. |
| `ai/prompt_builder.py` | Construye prompts para el LLM local | infra | 29 | MOVE | `infrastructure/whatsapp/ai/` | — |
| `application/confirm_order_use_case.py` | `ConfirmWhatsAppOrderUseCase` — orquesta confirmación de pedido + política de anticipo (con fallback local, ver leakage doc) | application (parcial) | 174 | REWRITE | `application/whatsapp/use_cases/confirm_order.py` | Ya tiene forma de caso de uso; el fallback de `_evaluate_advance_policy` (líneas 91-141) debe eliminarse y exigir el puerto de Pricing/Payments real, no calcularlo localmente. |
| `config/numbers.py` | `NumberRegistry` — resuelve número/canal por sucursal | infra | 106 | MOVE | `infrastructure/whatsapp/config/` | — |
| `config/schedules.py` | `ScheduleService` — horarios de sucursal (abre/cierra) | infra | 94 | MOVE | `infrastructure/whatsapp/config/` | Usado por `pedido_flow._apply_business_hours_policy`; es lectura de configuración operativa del ERP, no de WhatsApp — candidato a vivir detrás de un puerto hacia Operaciones/Sucursales. |
| `config/settings.py` | Config central: env vars, resolución credenciales ERP→env, helpers `is_production()`/`is_test()` | infra | 172 | REWRITE | `infrastructure/whatsapp/config/settings.py` + `infrastructure/whatsapp/secrets/secret_store.py` | Lee secretos (`meta_token`, `verify_token`, `internal_api_key`) con `sqlite3.connect` directo a la tabla `configuraciones` del ERP en cada llamada (líneas 54-76) — sin caching, sin `SecretStore` dedicado. Ver `whatsapp_security_audit.md`. |
| `domain/phone_number.py` | Shim de 7 líneas que re-exporta desde el módulo raíz `phone_number.py` | domain (vacío) | 7 | REWRITE | `domain/whatsapp/value_objects/phone_number.py` | **Invertido**: el código real vive en `whatsapp_service/phone_number.py` (raíz de paquete, no en `domain/`); este archivo es solo un `from phone_number import ...`. Además, `messaging/sender.py` y otros importan del módulo raíz directamente, no de `domain/`, así que hay dos rutas de import para lo mismo. Al mover a la arquitectura objetivo, el contenido real debe promoverse a `domain/whatsapp/value_objects/` y unificarse un único import. |
| `phone_number.py` (raíz) | Implementación real: `normalize_to_digits/e164/mx_local10`, `possible_match_key` | domain (mal ubicado) | 40 | MOVE | `domain/whatsapp/value_objects/phone_number.py` | Es lógica de dominio pura (sin I/O), correctamente aislada de framework — solo está en la carpeta equivocada. |
| `erp/adjustment_approval.py` | `AdjustmentApprovalService` — cliente acepta/rechaza ajuste de peso vía WA | application+infra mezclado | 156 | REWRITE | `application/whatsapp/use_cases/respond_delivery_adjustment.py` | Contiene fallback de cálculo de `pending_subtotal` (línea 81, ver leakage doc) y hace 2 `INSERT INTO wa_event_log` sin columna `id` que fallan silenciosamente contra el esquema real (ver `whatsapp_schema_consolidation.md`). |
| `erp/bridge.py` | `ERPBridge` — fachada de 1062 líneas que implementa 6 gateways (Customer/Order/Quote/Payment/Inventory/Delivery), con API-first + fallback SQLite | infrastructure (facade sobredimensionada) | 1062 | REWRITE | Dividir en `infrastructure/whatsapp/erp_clients/{customer,order,quote,payment,inventory,delivery}_client.py` + eliminar el fallback SQLite de negocio | El archivo con más riesgo del microservicio. Contiene: `calcular_anticipo_rules` (crédito + reglas de anticipo, líneas 860-893, **sin** gate de producción), fallback de `total = sum(cantidad*precio)` en `_crear_pedido_wa_impl`/`_crear_cotizacion_wa_impl` (líneas 472, 700), y el `_new_customer_id()` con `sys.path` hack (líneas 45-64). Ver `whatsapp_business_logic_leakage.md`. |
| `erp/business_orchestrator.py` | `BusinessOrchestrator` — coordina cotización→venta, anticipos, OC automática, delivery, forecast; emite todos los eventos de negocio | application (con lógica de negocio indebida) | 359 | REWRITE | Repartir entre `application/whatsapp/use_cases/*` (orquestación) y puertos hacia Sales/Payments/Procurement/Inventory (decisiones) | Llama `self.erp.calcular_anticipo_rules(...)` (líneas 161, 218) y genera OC automáticas vía `self.erp.generar_orden_compra` (dentro de `_verificar_y_generar_oc`, líneas 320-350) — decisiones de crédito/compras tomadas desde WhatsApp. Activo por default (`_check_flag` devuelve `True` si la fila no existe, línea 61). |
| `erp/events.py` | `WAEventEmitter` — publica al EventBus del ERP + persiste en `wa_event_log` | infra | 158 | REWRITE | `infrastructure/whatsapp/observability/event_emitter.py` | `ensure_tables()` (líneas 140-158) crea `wa_event_log` con `id INTEGER PRIMARY KEY AUTOINCREMENT`, **incompatible** con el esquema real ya creado por la migración 050 del ERP (`id TEXT NOT NULL PRIMARY KEY`) — el `INSERT` de `emit()` (líneas 118-122) omite la columna `id` y por tanto falla con `IntegrityError` en cualquier deploy donde la migración 050 ya corrió (que es el orden de arranque real en `main.py:76-84`). El error queda enmascarado por `except Exception: pass` (línea 127-128). Ver hallazgo detallado en `whatsapp_schema_consolidation.md`. |
| `erp/gateways/api_client.py` | `ERPApiClient` — helper HTTP hacia el ERP | infra | 18 | MOVE | `infrastructure/whatsapp/erp_clients/api_client.py` | No revisado línea a línea; 18 líneas, delgado. |
| `erp/gateways/customer_gateway.py` | Gateway cliente (composición sobre `ERPBridge._impl`) | infra | 18 | MOVE | `infrastructure/whatsapp/erp_clients/customer_client.py` | — |
| `erp/gateways/delivery_gateway.py` | Gateway delivery | infra | 35 | MOVE | `infrastructure/whatsapp/erp_clients/delivery_client.py` | — |
| `erp/gateways/inventory_gateway.py` | Gateway inventario | infra | 12 | MOVE | `infrastructure/whatsapp/erp_clients/inventory_client.py` | — |
| `erp/gateways/order_gateway.py` | Gateway pedidos | infra | 12 | MOVE | `infrastructure/whatsapp/erp_clients/order_client.py` | — |
| `erp/gateways/payment_gateway.py` | Gateway pagos/anticipos | infra | 59 | MOVE | `infrastructure/whatsapp/erp_clients/payment_client.py` | — |
| `erp/gateways/quote_gateway.py` | Gateway cotizaciones | infra | 12 | MOVE | `infrastructure/whatsapp/erp_clients/quote_client.py` | — |
| `erp/gateways/sqlite_connection.py` | Conexión SQLite compartida para gateways | infra | 12 | REWRITE | eliminar junto con el fallback SQLite de negocio | Solo tiene sentido mientras exista el fallback dev; en la arquitectura objetivo el microservicio no debería tocar SQLite del ERP directamente para escritura de negocio. |
| `erp/mappers.py` | Mapeo de payloads | infra | 17 | MOVE | `infrastructure/whatsapp/erp_clients/mappers.py` | — |
| `erp/pos_notifier.py` | `POSNotifier` — puente persistente WA→ERP desktop (event_log + inbox) | infra | 332 | REWRITE | `infrastructure/whatsapp/observability/pos_notifier.py` | Segunda definición divergente de `wa_event_log` (`CREATE TABLE` con `id INTEGER AUTOINCREMENT`, líneas 165-172) más el mismo bug de `INSERT` sin `id` (líneas 174-182). |
| `flows/base_flow.py` | Clase base de flujos conversacionales | conversations | 44 | MOVE | `conversations/whatsapp/flows/base.py` | No revisado en detalle línea a línea; base delgada. |
| `flows/cotizacion_flow.py` | Flujo cotización (armar → confirmar → aceptar/rechazar/convertir) | conversations (con cálculo de negocio) | 258 | REWRITE | `conversations/whatsapp/flows/quote_flow.py` | Calcula `total = sum(i.subtotal for i in ctx.cotizacion_items)` localmente (líneas 95, 113) — ver leakage doc. |
| `flows/delivery_flow.py` | `DeliveryBridge` — conecta pedido WA con delivery del ERP | application/conversations mezclado | 60 | MOVE | `application/whatsapp/use_cases/schedule_delivery.py` | Delega correctamente a `erp.delivery.schedule()` — es de los archivos más limpios del microservicio. |
| `flows/menu_flow.py` | Flujo menú principal | conversations | 148 | MOVE | `conversations/whatsapp/flows/menu_flow.py` | No revisado en detalle. |
| `flows/pago_flow.py` | Flujo método de pago + generación de link MercadoPago | conversations (con cálculo de negocio) | 121 | REWRITE | `conversations/whatsapp/flows/payment_flow.py` + `infrastructure/whatsapp/providers/mercadopago_client.py` | Construye el payload de preferencia de MercadoPago con `unit_price: ctx.total_pedido()` (línea 96, total calculado localmente en el propio contexto de conversación) en vez de re-consultar el total canónico de `ventas` antes de generar el link de cobro. |
| `flows/pedido_flow.py` | Flujo pedido completo (categoría→producto→cantidad→entrega→confirmación) | conversations (con cálculo de negocio) | 378 | REWRITE | `conversations/whatsapp/flows/order_flow.py` | Valida stock localmente (`prod.get("stock",0) < qty`, línea 153) y arma `PedidoItem` con precio tomado directo del catálogo (línea 167) — ver leakage doc. Es, junto a `bridge.py` y `business_orchestrator.py`, uno de los tres archivos con más lógica de negocio indebida. |
| `flows/registro_flow.py` | Flujo registro de cliente nuevo | conversations | 90 | MOVE | `conversations/whatsapp/flows/registration_flow.py` | No revisado en detalle. |
| `flows/repetir_flow.py` | Flujo "repetir último pedido" | conversations | 59 | MOVE | `conversations/whatsapp/flows/repeat_order_flow.py` | No revisado en detalle. |
| `flows/sucursal_flow.py` | Flujo selección de sucursal | conversations | 56 | MOVE | `conversations/whatsapp/flows/branch_selection_flow.py` | No revisado en detalle. |
| `messaging/interactive.py` | Construcción de mensajes interactivos (botones/listas) | infra | 188 | MOVE | `infrastructure/whatsapp/messaging/interactive_builder.py` | No revisado en detalle. |
| `messaging/sender.py` | `send_message/send_text/send_buttons/send_list/send_template` — cliente HTTP hacia Meta Graph API | infra | 356 | REWRITE | `infrastructure/whatsapp/providers/meta_cloud_api_sender.py` | Resuelve credenciales con 3 niveles de fallback en cada envío (líneas 56-108, sin cache), tiene `sys.path` hack propio (línea 154) duplicando el de `bridge.py`/`events.py`, e incluye el gate de consentimiento CRM-31 (`_is_whatsapp_opted_out`, líneas 125-169) que es la única pieza de consentimiento real hoy — debe preservarse explícitamente al reescribir. |
| `messaging/templates.py` | Definición de templates pre-aprobados | infra | 108 | MOVE | `infrastructure/whatsapp/messaging/templates.py` | No revisado en detalle; hay test dedicado `test_templates_parameter_validation.py`. |
| `middleware/auth.py` | `require_internal_key` — dependencia FastAPI para X-Internal-Key | infra (código muerto) | 20 | DELETE | — | Confirmado por grep: **no se usa como dependencia en ningún router**. `notify_router.py` y `delivery_router.py` reimplementan su propia validación inline (`_check_internal_key`) en vez de usar esta función. Es duplicación no intencional — eliminar o, si se prefiere, consolidar en él y hacer que los routers lo usen. |
| `middleware/handoff.py` | `HandoffService` — traspaso a humano | application | 39 | MOVE | `application/whatsapp/services/handoff_service.py` | No revisado en detalle; el prompt maestro pide handoff humano como requisito — validar cobertura real en fase de diseño. |
| `middleware/hmac_validator.py` | `verify_signature` (Meta) + `verify_mp_signature` (MercadoPago) | infra | 41 | REUSE | `infrastructure/whatsapp/security/hmac_validator.py` | Implementación correcta (HMAC-SHA256, `compare_digest`). Es la única validación HMAC real del sistema — pero **no** se usa para autenticar el canal interno ERP↔microservicio (`X-Internal-Key` es comparación de string plano, no HMAC). Ver `whatsapp_security_audit.md`. |
| `middleware/rate_limiter.py` | `RateLimiter` — límite de mensajes/minuto + filtros de status/grupo | infra | 70 | MOVE | `infrastructure/whatsapp/security/rate_limiter.py` | No revisado en detalle. |
| `models/context.py` | `ConversationContext`, `PedidoItem`, `FlowState` | conversations (con cálculo de negocio) | 124 | REWRITE | `conversations/whatsapp/state/context.py` (estado) — `PedidoItem.subtotal`/`total_pedido()` deben dejar de ser autoridad de precio | 121-125 | `PedidoItem.subtotal` (línea 50-51, `cantidad*precio_unitario`) y `ConversationContext.total_pedido()` (línea 114-115) son la raíz de la mayoría de los cálculos de dinero hechos en WhatsApp. Ver leakage doc. |
| `models/message.py` | `IncomingMessage`/`OutgoingMessage` | conversations | 121 | MOVE | `conversations/whatsapp/models/message.py` | No revisado en detalle. |
| `notifications/alerts.py` | Alertas operativas | application | 86 | MOVE | `application/whatsapp/notifications/alerts.py` | No revisado en detalle. |
| `notifications/customer.py` | Notificaciones a cliente | application | 42 | MOVE | `application/whatsapp/notifications/customer.py` | No revisado en detalle; usado por `webhook/mercadopago.py`. |
| `notifications/rrhh.py` | Notificaciones RRHH | application | 24 | MOVE | `application/whatsapp/notifications/hr.py` | No revisado en detalle. |
| `notifications/staff.py` | Notificaciones a staff | application | 35 | MOVE | `application/whatsapp/notifications/staff.py` | No revisado en detalle. |
| `parser/intent_parser.py` | `IntentParser` — combina reglas + matcher + IA | application | 164 | MOVE | `application/whatsapp/nlp/intent_parser.py` | No revisado en detalle. |
| `parser/llm_local.py` | `OllamaClient` — cliente LLM local (DeepSeek) | infra | 159 | MOVE | `infrastructure/whatsapp/ai/ollama_client.py` | No revisado en detalle. |
| `parser/patterns.py` | Patrones regex de intents | domain/infra | 136 | MOVE | `infrastructure/whatsapp/nlp/patterns.py` | No revisado en detalle. |
| `parser/product_matcher.py` | `ProductMatcher` — búsqueda difusa de productos contra catálogo ERP | infra (consulta directa a `productos`) | 131 | MOVE | `infrastructure/whatsapp/erp_clients/product_catalog_client.py` | Usado también desde `pedido_flow.py` con `ProductMatcher(self.erp.db, ...)` — acceso directo a `self.erp.db`, acoplado a SQLite del ERP. |
| `router/delivery_router.py` | Endpoints REST de ajustes/delivery hacia WA | api | 247 | REWRITE | `api/whatsapp/routers/delivery.py` | Reimplementa su propia `_check_internal_key` (líneas 44-62), duplicado del mismo patrón en `notify_router.py`. |
| `router/message_router.py` | `MessageRouter` — pipeline central de enrutamiento de mensajes entrantes | application | 366 | REWRITE | `application/whatsapp/services/message_router.py` | No revisado línea a línea en esta fase (366 líneas); la auditoría previa (FASE 7, 2026-05-28) documenta que ya tiene un pipeline de middlewares parcial (`MessageMiddleware`, `NotificationNumberGuard`, `AdjustmentResponseMiddleware`, `BranchSelectionMiddleware`, `CancelFlowMiddleware`, `CustomerIdentificationMiddleware`) — pendiente de verificar contra el código actual en fase de diseño. |
| `router/notify_router.py` | Endpoints REST `/api/notify/*` (ERP→WA) | api | 128 | REWRITE | `api/whatsapp/routers/notify.py` | Auth interna con fail-open si la key no está configurada (líneas 39-44, ver security doc). Reimplementa `_check_internal_key` en vez de usar `middleware/auth.py`. |
| `router/number_router.py` | `NumberRouter` — resuelve número/canal para un mensaje entrante | application | 27 | MOVE | `application/whatsapp/services/number_router.py` | No revisado en detalle. |
| `state/business_idempotency.py` | `BusinessIdempotencyService` — idempotencia persistente de acciones críticas | application | 135 | REUSE (mover) | `application/whatsapp/services/idempotency_service.py` | Tabla `wa_business_idempotency` con PK `INTEGER AUTOINCREMENT` — no cumple UUIDv7 (ver schema doc). Lógica (`get/start/complete/fail/run_once`) es sólida y debe conservarse. |
| `state/conversation.py` | `ConversationStore` — persistencia de contexto + dedupe de mensajes | infra | 157 | MOVE | `infrastructure/whatsapp/persistence/conversation_store.py` | Tablas `conversations` (PK `phone` TEXT, aceptable) y `message_log` (PK `INTEGER AUTOINCREMENT`, no UUIDv7). |
| `state/priority_queue.py` | Cola de prioridad para mensajes | infra | 88 | MOVE | `infrastructure/whatsapp/messaging/priority_queue.py` | No revisado en detalle. |
| `state/reminder_engine.py` | Motor de recordatorios programados (anticipo pendiente, entrega, confirmación) | application | 334 | MOVE | `application/whatsapp/services/reminder_engine.py` | No revisado en detalle (334 líneas); usado extensamente desde `pedido_flow.py`/`cotizacion_flow.py` vía `self.reminders.programar_*`. |
| `webhook/mercadopago.py` | Webhook de confirmación de pago MercadoPago | api (con lógica de negocio) | 157 | REWRITE | `api/whatsapp/webhooks/mercadopago.py` | Resuelve `venta_id` por *heurística* de teléfono + `LIKE` (líneas 104-114, "buscar venta_id por teléfono... no es fiable con múltiples pedidos abiertos"); confía en `external_reference` como teléfono plano. Fail-open si `MP_WEBHOOK_SECRET` no está configurado (líneas 41-45). |
| `webhook/whatsapp.py` | Webhook oficial Meta (`GET`/`POST /webhook`) | api | 119 | REUSE (mover) | `api/whatsapp/webhooks/meta.py` | El mejor archivo del microservicio en cuanto a seguridad: verify-token con `hmac.compare_digest` (línea 53), firma `X-Hub-Signature-256` verificada si `WA_APP_SECRET` está seteado (líneas 68-72, pero **no** es obligatorio — fail-open si no está seteado), dedupe por `message_id`, rate limiting. |
| `tests/*.py` (15 archivos) | Suite de tests del microservicio | tests | ~1300 (suma) | REUSE | `whatsapp_service/tests/` (o `tests/whatsapp/` si se reorganiza) | No se auditó cobertura real en esta fase; los nombres sugieren cobertura de: idempotencia de negocio (`test_bridge_create_cliente_minimo`), notificaciones (`test_bridge_notification_routing`, `test_pos_notifier_dedupe`), cotización (`test_cotizacion_flow_phase6`, `test_conversation_quote_context`), IA (`test_ai_*`, `test_intent_resolver*`), seguridad (`test_mercadopago_webhook_signature`, `test_sender_consent_gate`), router (`test_message_router_*`), templates (`test_templates_parameter_validation`), ajustes (`test_adjustment_approval_phase7`). |

---

## 2. ERP (`pos_spj_v13.4/`) — lado legacy

| Archivo | Rol | Líneas | Clasificación | Destino / disposición | Notas |
|---|---|---|---|---|---|
| `core/services/whatsapp_service.py` | Servicio unificado v12: `WhatsAppConfig`, `MessageQueue` (cola offline-first con backoff, tabla `whatsapp_queue`), `WhatsAppService` (envío Meta/Twilio directo por `urllib`/`twilio.rest`, worker daemon), `WebhookHandler`/`WhatsAppWebhookServer` (`HTTPServer` propio en puerto 8767, **sin validación de firma HMAC en absoluto** — solo compara `verify_token` en el `GET`) | 526 | BLOCKED | — | **Causa del bloqueo**: es simultáneamente (a) el emisor real de TODAS las notificaciones salientes iniciadas por el ERP (nómina, arqueos, recordatorios de compra — ver `core/app_container.py:920-1014`) vía `NotificationService`, y (b) un segundo servidor de webhook activo en producción (`main.py:184-188`). No se puede clasificar como DELETE sin antes migrar el camino de notificaciones salientes del ERP hacia el microservicio (`/api/notify/*`) y decidir explícitamente apagar `WhatsAppWebhookServer`. **Riesgo**: mientras siga arrancando, puede procesar mensajes entrantes con un bot completamente distinto (Rasa/`bot_pedidos.py`) al que corre en `whatsapp_service/`, produciendo respuestas duplicadas o contradictorias al mismo cliente si algún tráfico llega a este puerto. **Responsable sugerido**: decisión de producto/ops sobre cuál es el único webhook autorizado + qué reemplaza el envío saliente. **Dependencia**: `core/app_container.py`, `core/services/notification_service.py`, `services/bot_pedidos.py`. **Condición de eliminación**: (1) todo el envío saliente del ERP migrado a `POST /api/notify/*` del microservicio oficial; (2) `WhatsAppWebhookServer.start()` eliminado de `main.py`; (3) confirmación de que Meta no tiene registrada la URL de este servidor. |
| `services/whatsapp_service.py` | Shim de 7 líneas, re-exporta desde `core/services/whatsapp_service.py` | 7 | WRAP_TEMPORARILY | — | Preservar mientras exista `core/services/whatsapp_service.py` (regla explícita de CLAUDE.md §8-9: 3 shims de WhatsApp son intencionales). |
| `integrations/whatsapp_service.py` | Shim de 7 líneas, ídem | 7 | WRAP_TEMPORARILY | — | Ídem. |
| `core/integrations/whatsapp_client.py` | `WhatsAppClient` — cliente REST liviano (sin deps externas, `urllib`) hacia `/api/notify/*` del microservicio | 195 | REUSE | `infrastructure/erp_clients/whatsapp_channel_client.py` (lado ERP) | Bien escrito: resuelve `X-Internal-Key` en 4 niveles (parámetro > `configuraciones.wa_internal_api_key` > env > `.env` del microservicio) — es el consumidor "correcto" del canal REST oficial. |
| `core/services/pedidos_whatsapp_service.py` | `PedidosWhatsappService` — UI-facing, opera sobre `pedidos_whatsapp`/`pedidos_whatsapp_items` (ajuste de pesos, asignar repartidor) | 76 | BLOCKED | — | **Causa**: pertenece al pipeline legacy de pedidos (tablas `pedidos_whatsapp*`, alimentadas por `core/use_cases/pedido_wa.py` / `services/bot_pedidos.py` / `rasa/actions/actions.py`), completamente paralelo al pipeline nuevo (`ventas`/`detalles_venta` vía `whatsapp_service`). `ajustar_pesos()` (líneas 44-68) recalcula `subtotal = peso*precio` y el total del pedido directamente en SQL. **Riesgo**: si ambos pipelines de pedidos siguen vivos, un mismo negocio tiene dos fuentes de verdad de "pedido entrante por WhatsApp" con esquemas de tablas distintos. **Responsable sugerido**: decisión de producto sobre si el flujo de mostrador/pesaje por `pedidos_whatsapp` sigue siendo necesario o se reemplaza por el flujo de `ventas` + delivery adjustments (`whatsapp_service/erp/adjustment_approval.py`, que ya cubre "ajuste de peso" contra `delivery_items`). **Dependencia**: `core/use_cases/pedido_wa.py`, UI `VentanaPedidos` (no localizada/auditada en esta fase — requiere verificación). **Condición de eliminación**: confirmar que ningún flujo operativo real sigue creando filas en `pedidos_whatsapp` antes de borrar el servicio. |
| `core/use_cases/pedido_wa.py` | Caso de uso CQRS legacy: crea pedido en `pedidos_whatsapp`/`pedidos_whatsapp_items` (UUIDv7 ya aplicado, línea ~120) | 228 | BLOCKED | — | Mismo bloqueo que la fila anterior — es la escritura que alimenta ese pipeline paralelo. Usado también por `tests/test_flujo_completo.py` y `webapp/api_pedidos.py` (una API web adicional, no auditada en profundidad en esta fase — **requiere verificación**). |
| `services/bot_pedidos.py` | Bot conversacional legacy completo (pedido + cotización + anticipos + horarios de sucursal + recordatorios) que alimenta `pedidos_whatsapp` | 893 | BLOCKED | — | No se leyó línea por línea (fuera de presupuesto de esta fase; se confirmó por grep que está wireado en `core/app_container.py:695-700` y que inserta en `pedidos_whatsapp`). Es, en tamaño, el flujo conversacional más grande de todo el repo — mayor que la suma de todos los `flows/*.py` del microservicio oficial. **Causa del bloqueo**: decidir si esta lógica (horarios, anticipos, cotización) ya está 100% cubierta por los flows nuevos antes de poder borrarla seguro. **Responsable sugerido**: producto, comparando feature-a-feature contra `whatsapp_service/flows/pedido_flow.py` + `cotizacion_flow.py`. **Condición de eliminación**: paridad de features confirmada + tráfico real verificado en 0 sobre este camino. |
| `rasa/actions/actions.py` | Servidor de acciones Rasa SDK (`rasa run actions --port 5055`), conexión SQLite propia (`SPJ_DB_PATH`, default `data/spj.db` — **no** la ruta canónica del ERP) | 532 | BLOCKED | — | **Causa**: proceso externo independiente (no es parte del árbol de imports Python normal; solo se activa si alguien ejecuta `rasa run actions`). Invocado opcionalmente por `core/services/whatsapp_service.py:353-365` vía HTTP a `localhost:5005`. **Riesgo**: `DB_PATH` por defecto apunta a una ruta relativa distinta a la BD canónica documentada en `whatsapp_service/config/settings.py` — alto riesgo de "split-brain" de datos si alguna vez se ejecuta contra un working directory distinto al esperado. **Responsable sugerido**: decisión de producto sobre si Rasa sigue siendo parte del stack (el prompt maestro no lo menciona como requisito del bounded context objetivo). **Condición de eliminación**: confirmar que no hay ningún despliegue activo corriendo `rasa run actions`, y remover la llamada `forward_to_rasa` de `core/services/whatsapp_service.py`. |
| `core/services/whatsapp_admin_service.py` | `WhatsAppAdminService` — facade de administración para la UI (números, config, historial, métricas) | 74 | REUSE | `infrastructure/whatsapp_admin/` (lado ERP, no forma parte del bounded context de mensajería en sí, es panel de administración) | Sin SQL directo, delega a repos — ya cumple regla de capas. |
| `core/services/whatsapp_credential_service.py` | `WhatsAppCredentialService` — guarda/enmascara/valida/rota credenciales Meta | 134 | REUSE | `infrastructure/whatsapp_admin/credential_service.py`, o consolidar con el futuro `SecretStore` del microservicio | Enmascarado correcto (`_mask_token`, nunca loguea token completo); validación contra Graph API real. Es el candidato más cercano a un `SecretStore` real, pero hoy vive del lado ERP (SQLite `whatsapp_numeros`/`configuraciones`), no del lado del microservicio que es quien realmente necesita los secretos en runtime. |
| `core/repositories/whatsapp_config_repository.py` | CRUD `whatsapp_numeros` + `configuraciones` (prefijo `wa_`) | 147 | REUSE | `infrastructure/whatsapp_admin/config_repository.py` | Bien parametrizado, sin SQL injection. |
| `core/repositories/whatsapp_history_repository.py` | Historial unificado leyendo `wa_message_queue` → `bot_mensajes_log` → `pedidos_whatsapp` | 93 | REWRITE | `infrastructure/whatsapp_admin/history_repository.py` | Su primera fuente, `wa_message_queue`, **no existe en ningún archivo de migración** (confirmado por grep en `migrations/`) — es una tabla fantasma; toda consulta a ella falla silenciosamente (`except Exception: pass`, línea 27-28) y cae al siguiente fallback. En la práctica esto siempre lee de `bot_mensajes_log` o `pedidos_whatsapp` (ambas del pipeline legacy), nunca refleja actividad del microservicio nuevo (`message_log`/`conversations`). |
| `core/repositories/whatsapp_metrics_repository.py` | Métricas combinadas: `ventas` (canal=whatsapp), `wa_message_queue` (fantasma), `conversations.db` del microservicio, fallback a tablas legacy | 166 | REWRITE | `infrastructure/whatsapp_admin/metrics_repository.py` | Mismo problema de `wa_message_queue` fantasma en `_queue_metrics()` (línea 70-77). Sí lee correctamente `message_log`/`conversations` del microservicio vía `conversations.db` (líneas 80-119) cuando existe — es la única pieza del lado admin que efectivamente refleja actividad del microservicio nuevo. |
| `notifications/whatsapp_channel.py` | `WhatsAppNotificationChannel` — adapta al framework `NotificationChannel`, delega a `DeliveryWhatsAppService` | 66 | REUSE | `infrastructure/notifications/whatsapp_channel.py` | Limpio; no ejecuta SQL ni calcula dinero. |
| `core/services/delivery_whatsapp_service.py` | `DeliveryWhatsAppService` — facade legacy-compatible sobre `WhatsAppDeliveryNotifier` | 74 | REUSE | consolidar con `core/delivery/infrastructure/whatsapp_delivery_notifier.py` | Delgado, delega correctamente. |
| `modulos/whatsapp/whatsapp_module.py` | `ModuloWhatsApp` — UI PyQt5 real (7 tabs: Estado, Credenciales, Números, Políticas, Webhook, Historial, Diagnóstico) | 140 | REUSE | `ui/qt5/whatsapp/` (sin cambios de lógica) | Confirmado como la UI **efectivamente wireada**: `interfaz/main_window.py:157` importa `from modulos.whatsapp_module import ModuloWhatsApp` (el shim), que a su vez re-exporta desde este archivo (`modulos/whatsapp/__init__.py`). Sin SQL directo, delega a `WhatsAppAdminService`/`WhatsAppCredentialService`. |
| `modulos/whatsapp_module.py` | Shim de 5 líneas, re-exporta `ModuloWhatsApp` desde `modulos/whatsapp/whatsapp_module.py` | 5 | WRAP_TEMPORARILY | — | Es el import real usado por `interfaz/main_window.py:157`. No está en la lista de "3 shims intencionales" del CLAUDE.md (esos son a nivel `services/`/`integrations/`), pero cumple el mismo rol de compatibilidad — mantener mientras no se decida aplanar el paquete `modulos/whatsapp/`. |

---

## 3. Contexto Delivery (integración con canal WhatsApp)

| Archivo | Rol | Líneas | Clasificación | Destino | Notas |
|---|---|---|---|---|---|
| `core/delivery/application/sync_whatsapp_orders.py` | `SyncWhatsAppOrdersUseCase` — pull de pedidos WA hacia `delivery_orders`, o sync de ventas pendientes | 90 | REUSE | `application/orders_delivery/use_cases/sync_whatsapp_orders.py` (ya en su bounded context correcto: Orders/Delivery) | Correcto: no calcula dinero, solo orquesta upsert + eventos. |
| `core/delivery/infrastructure/whatsapp_delivery_notifier.py` | `WhatsAppDeliveryNotifier` — templates de notificación de estado de entrega, delega envío a `WhatsAppClient` | 149 | REUSE | `infrastructure/orders_delivery/notifiers/whatsapp_delivery_notifier.py` | Formatea montos ya calculados (recibidos como parámetro), no los calcula — no es leakage. |
| `core/events/handlers/whatsapp_notification_handler.py` | `WhatsAppNotificationHandler` — aplica `NotificationPolicyService` antes de cualquier envío WA a staff | 174 | REUSE | `application/notifications/handlers/whatsapp_notification_handler.py` | Ejemplar de separación correcta: "el microservicio WhatsApp NO decide a quién notificar" (comentario propio del archivo, línea 6-7). |
| `backend/infrastructure/integrations/orders_delivery_whatsapp_client.py` | Cliente WA específico del bounded context Orders/Delivery nuevo (`backend/`) | 79 | REUSE | ya en capa correcta | No revisado línea a línea en esta fase — nombre y ubicación ya siguen la convención objetivo (`backend/infrastructure/integrations/`). |
| `backend/application/customers/queries/customer_whatsapp_summary_query.py` | Query de resumen WhatsApp para Customer 360 | 62 | REUSE | ya en capa correcta | Ídem, no revisado en profundidad; ubicación ya correcta. |

---

## 4. Migraciones (`pos_spj_v13.4/migrations/standalone/`)

| Archivo | Tablas creadas/alteradas | Clasificación | Notas |
|---|---|---|---|
| `036_whatsapp_rasa.py` | `whatsapp_queue`, `rasa_sessions`, `marketing_messages` | REUSE (ajustar en fase de esquema) | `whatsapp_queue` con PK `TEXT` (UUIDv7-compatible) ya. `rasa_sessions` es dependencia exclusiva de la integración Rasa (bloqueada arriba). |
| `042_whatsapp_multicanal.py` | `whatsapp_numeros`, vista `v_whatsapp_config` | REUSE | PK `TEXT`, ya UUIDv7-compatible. |
| `050_wa_integration.py` | `wa_event_log` (PK `TEXT`), `wa_reminder_queue` (PK `TEXT`), `ordenes_compra` (PK `TEXT` — si no existía), columnas en `cotizaciones`/`ventas`/`anticipos` | REUSE (con fix urgente) | Ver bug crítico en `whatsapp_schema_consolidation.md`: el código en `erp/events.py` y `erp/pos_notifier.py` asume un esquema `INTEGER AUTOINCREMENT` distinto al que esta migración realmente crea. |
| `081_wa_queue_backoff.py` | Agrega `proxima_revision` a `whatsapp_queue` | REUSE | Correcto, aditivo e idempotente. |
| `086_whatsapp_order_sales_columns.py` | Agrega columnas a `ventas` (`tipo_entrega`, `canal`, `anticipo_pagado`, etc.) | REUSE | Correcto. |
| `087_whatsapp_sale_detail_columns.py` | Agrega `nombre` a `detalles_venta` + backfill | REUSE | Correcto. |
| `090_whatsapp_delivery_workflow_columns.py` | Agrega `workflow_type`/`scheduled_at`/`source_channel` a `ventas` y `delivery_orders` | REUSE | Correcto. |

No se encontró ninguna migración `050` o `081` con nombre distinto al documentado — la auditoría previa (`WHATSAPP_AUDIT.md`) estaba correcta en los números de archivo. También se confirmó (m000_base_schema.py) que las tablas `pedidos_whatsapp`/`pedidos_whatsapp_items` (líneas 1093-1130) y `bot_sessions`/`whatsapp_queue`/`links_pago` (líneas 1132-1160) ya existen desde el esquema base (`m000`), con PK `TEXT` — es decir, el esquema base ya nació "UUIDv7-friendly" en tipos de columna, aunque como se ve en §0 esas tablas alimentan el pipeline legacy paralelo.

---

## 5. Tests relacionados con WhatsApp fuera de `whatsapp_service/tests/`

| Archivo | Notas |
|---|---|
| `pos_spj_v13.4/tests/test_wa_bridge.py`, `test_wa_client.py`, `test_wa_flows.py`, `test_wa_orchestrator.py`, `test_wa_parser.py`, `test_wa_phase5_use_case.py`, `test_wa_phase9_regression.py`, `test_wa_refactor.py`, `test_wa_repositories.py`, `test_wa_webhook.py` | Confirmados existentes (no renombrados respecto a la auditoría previa). No se determinó en esta fase si testean el microservicio (`whatsapp_service/`) o el legacy ERP-embebido — el nombre `test_wa_*` es ambiguo entre ambos; **requiere verificación** en fase de diseño de tests de regresión. |
| `pos_spj_v13.4/tests/test_remediacion_c_wa_uuid.py` | No mencionado en el contexto previo de esta tarea — nuevo hallazgo. Nombre sugiere regresión específica de migración a UUIDv7 en tablas WA. No leído en detalle. |
| `pos_spj_v13.4/tests/test_delivery_whatsapp_notifier.py` | Testea `core/delivery/infrastructure/whatsapp_delivery_notifier.py`. |
| `pos_spj_v13.4/tests/unit/test_orders_delivery_whatsapp_client.py` | Testea `backend/infrastructure/integrations/orders_delivery_whatsapp_client.py`. |
| `pos_spj_v13.4/tests/test_flujo_completo.py` | Referencia `core/use_cases/pedido_wa.py` — cubre (parcialmente) el pipeline legacy paralelo. |

---

## Resumen de clasificación

| Clasificación | Cantidad aproximada de archivos |
|---|---|
| REUSE | ~20 |
| MOVE | ~35 |
| WRAP_TEMPORARILY | 4 (los 3 shims de `whatsapp_service.py` + shim `modulos/whatsapp_module.py`) |
| REWRITE | ~20 |
| DELETE | 1 (`whatsapp_service/middleware/auth.py`, código muerto confirmado) |
| BLOCKED | 5 (`core/services/whatsapp_service.py`, `core/services/pedidos_whatsapp_service.py`, `core/use_cases/pedido_wa.py`, `services/bot_pedidos.py`, `rasa/actions/actions.py`) |

Los 5 `BLOCKED` comparten una misma causa raíz: **no se puede decidir su eliminación sin antes
resolver, a nivel de producto, cuál de los tres pipelines de pedidos por WhatsApp (§0) es el único
autorizado**. Mientras esa decisión no se tome, cualquier intento de "solo borrar el legacy" en
FASE 1+ arriesga perder funcionalidad operativa real (notificaciones salientes de nómina/arqueo,
escalación a gerente, flujo de pesaje de mostrador) sin habérsela migrado primero — lo cual violaría
la regla de PRIORIDAD 0 del CLAUDE.md del proyecto.
