# Matriz de brechas — `whatsapp.md` (canal y microservicio WhatsApp, §1–§81)

- **Fecha:** 2026-11-01 · **Commit base:** `6816e125` · **Rama:** `sdlc/sdlc-ui-001` (solo `docs/sdlc/`)
- **Método:** `/sdlc-plan arquitectura docs/sdlc/inputs/whatsapp.md` (modo C). Cinco subagentes de lectura en paralelo, por grupo de secciones: (A) §2, §7–§8, §17–§18, §20, §23, §52–§54, §58–§59, §73–§74, §78; (B) §9–§16, §19, §21, §55–§56, §60–§61, §75; (C) §22, §24–§32, §50–§51, §62–§64; (D) §1–§2, §33–§48, §57; (E) §49, §65–§72, §74 y documentación. Los informes `docs/refactor/WA-0…22_*.md` (pipeline de septiembre) **no** se tomaron como evidencia: se auditó el código. Los hallazgos que sostienen ítems P0/P1 se volvieron a leer directamente al consolidar.
- **Rutas:** las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio; el resto, a `pos_spj_v13.4/`.
- **El documento trae su propio orden de fases** (§76, WA-0…22). Se respeta como orden de dependencias en la columna «Depende de» del backlog, pero cada fase se ejecuta como ítems SDLC, nunca como una corrida larga.
- **El documento cita rutas que ya no existen:** `core/services/whatsapp_service.py`, `services/whatsapp_service.py`, `integrations/whatsapp_service.py`, `core/integrations/whatsapp_client.py`, `core/services/pedidos_whatsapp_service.py`, `core/services/delivery_whatsapp_service.py`, `notifications/whatsapp_channel.py`, `modulos/whatsapp/`, `core/use_cases/pedido_wa.py` y `core/services/microservice_launcher.py` están **borrados** (verificado con `test -e`). Los paquetes `core/`, `services/`, `integrations/`, `modulos/` ya no existen, pero el microservicio todavía importa `core.*` en cuatro archivos.

Estados: `implementado y probado` · `parcial` · `documentado no implementado` · `defectuoso` · `duplicado` · `ausente`.

## Mediciones ejecutadas en esta sesión

| Medición | Resultado |
|---|---|
| `python -m pytest whatsapp_service/tests -q` (raíz) | **se interrumpe en la recolección**: `test_adjustment_approval_phase7.py` → `ModuleNotFoundError: No module named 'core'` (`whatsapp_service/erp/adjustment_approval.py:15`) |
| ídem con `--continue-on-collection-errors` | **699 passed, 15 failed, 1 error** (105 s). Fallas: `test_intent_resolver_ai_paths.py` (5), `test_message_router_intent_resolver_integration.py` (2), `test_wa_event_log_insert.py` (2), y 1 en `test_bridge_notification_routing`, `test_conversation_quote_context`, `test_cotizacion_flow_phase6`, `test_intent_resolver`, `test_mercadopago_webhook_signature`, `test_message_router_branch_switch` |
| `python -m pytest tests/architecture/test_whatsapp_runtime_imports.py tests/test_wa_{bridge,client,flows,orchestrator,parser,phase5_use_case,phase9_regression,admin_bounded_context_visibility}.py tests/test_delivery_whatsapp_notifier.py tests/test_remediacion_c_wa_uuid.py -q` (desde `pos_spj_v13.4/`) | **41 passed, 15 failed, 32 errors** (92 s). Errores: `test_wa_bridge.py` (29), `test_wa_client.py`, `test_wa_admin_bounded_context_visibility.py`, `test_delivery_whatsapp_notifier.py`. Fallas: `test_wa_parser.py` (7), `test_remediacion_c_wa_uuid.py` (3), `test_wa_orchestrator.py` (2), `test_wa_phase9_regression.py` (2), `test_whatsapp_runtime_imports.py` (1) |
| `.github/workflows/ci-segmented.yml` | **no corre `whatsapp_service/tests`** (77 archivos) **ni** `tests/test_wa_*.py`; solo 5 archivos del ERP sobre WhatsApp entran por `tests/{unit,integration}` |
| Guardias de §78 | **0 de 20** existen; la guardia de imports existente falla |

## Resumen

**Lectura general.** El canal tiene **dos arquitecturas en paralelo** y la viva es la legacy.

1. **Stack canónico de septiembre (WA-1…20):** dominio (`whatsapp_service/domain/whatsapp/`, 14 entidades, 25 intenciones, 12 estados de conversación), esquema limpio (`backend/infrastructure/db/schema/whatsapp_schema.py`, 18 tablas TEXT PK), `WebhookProcessor`, `InboxWorker`, `ConversationEngine`, resolución de intención por capas, `OutboundDispatcher`, `HandoffCoordinator`, consentimiento y clientes ERP. Lo arma `WhatsAppCompositionRoot` (41 servicios) y **solo lo usan `/health`, `/diagnostics` y `/api/notify/v2`, que no tiene llamadores**. Tiene buenas pruebas unitarias, con fakes.
2. **Camino vivo:** `main.py` → `webhook/whatsapp.py` → `router/message_router.py` → `flows/*` → `erp/bridge.py`. Procesa en línea, escribe 24 sentencias DML en tablas del ERP, calcula precio, existencia, totales, crédito y anticipo en el canal, toma la sucursal 1 por defecto, resuelve clientes por sufijo de teléfono y descarta mensajes. El ERP le habla por `/api/notify` v1, sin outbox.
3. **En el ERP no hay módulo WhatsApp**: ni menú, ni bandeja, ni respuesta humana, ni permisos del canal, ni auditoría. El panel legacy se borró sin reemplazo.

**Mayor riesgo.** El precio de la conversación se vuelve precio de registro (SDLC-WA-021, P0) y un pago de Mercado Pago confirma la venta con cualquier monto (ampliación de SDLC-WA-001, P0). Le siguen: cliente equivocado por sufijo de teléfono (WA-012), sucursal 1 inventada (WA-013), handoff prometido que nunca ocurre (WA-036), alta sin aviso de privacidad (WA-034) y sin forma de darse de baja (WA-035).

**Lo que sí está bien y se conserva:** firma `X-Hub-Signature-256` en tiempo constante; HMAC ERP→WA con timestamp, nonce y allowlist de servicio (`whatsapp_service/middleware/service_auth.py:57-142`); `SecretStore` para seis secretos con revocación; el esquema canónico; el outbox de productos (`product_whatsapp_outbox`, la única cola que de verdad se drena); `customer_whatsapp_summary_query` con `require()` en backend.

| Sección | Requisitos | Implementado y probado | Brechas → ítems |
|---|---|---|---|
| §1–§4 Principio, contexto, auditoría | 4 | 0 | WA-021, WA-050, WA-051 |
| §5–§8 Contextos, arquitectura, main, composición | 4 | 0 | WA-016, WA-007 (ampliado) |
| §9–§16 IDs, cuentas, números, identidad, teléfono, conversación, mensajes, privacidad | 8 | 0 | WA-011, WA-012, WA-013, WA-014, WA-006 (ampliado) |
| §17–§23 Webhook, seguridad, idempotencia, asíncrono, inbox/outbox, gateway, secretos | 7 | 0 | WA-002 (sin cambios), WA-006, WA-008, WA-010, WA-018, WA-019 |
| §24–§32 Plantillas, motor, intenciones, IA, contexto, menú | 9 | 0 | WA-020, WA-022, WA-023, WA-024, WA-025 |
| §33–§46 Catálogo, pedidos, peso, cotizaciones, pagos, crédito, delivery, direcciones, lealtad, clientes, consentimiento | 14 | 0 | WA-001/003/004/005 (ampliados), WA-021, WA-028…035, PAY-025 (ampliado), CRM-003 (ampliado) |
| §47–§51 Handoff, agentes, bandeja, notificaciones, alertas | 5 | 0 | WA-036, WA-037, WA-038, WA-040, WA-041, ORD-006 (ampliado) |
| §52–§61 API interna, auth, identidad de servicio, eventos, observabilidad, health, rate limit, retries, dead letter | 10 | 0 | WA-003, WA-009, WA-015, WA-017, WA-039, WA-046 |
| §62–§64 Media, archivos, horarios | 3 | 0 | WA-026, WA-027 |
| §65–§73 Módulo, navegación, KPI, UI, composer, permisos, segregación, auditoría, errores | 9 | 0 | WA-041…WA-045, WA-047; ARQ-PERM-001 (enlazado) |
| §74–§81 Legacy, tablas, fases, pruebas, guardias, DoD, reporte | 8 | 0 | WA-014, WA-048, WA-049, WA-050, WA-051 |

Ningún requisito queda en `implementado y probado`: lo que está construido no corre en el camino vivo, y lo que corre no tiene pruebas en CI.

## §1–§4 Principio rector, contexto no negociable y auditoría

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §1 | WhatsApp conversa; los contextos deciden; no replica negocio | defectuoso | 24 DML + 1 DDL sobre tablas del ERP en 7 archivos (`whatsapp_service/erp/bridge.py` 13, `erp/gateways/payment_gateway.py` 3, `erp/adjustment_approval.py` 3, `flows/cotizacion_flow.py:198`, `ai/intent_resolver.py:41`, `erp/pos_notifier.py:229,270`); precio `erp/catalog_sql.py:39-49`, existencia `:52-59`, totales `models/context.py:53-54`, crédito `erp/bridge.py:358-363`, anticipo `:858-890` | ninguna | WA-021, WA-028, WA-029, WA-031, WA-050 |
| §2 | Un webhook, un sender, una cola, un sistema de eventos; sin SQL del ERP, sin `sys.path`, sin fallbacks a SQLite | defectuoso | dos webhooks (`webhook/whatsapp.py:33,63` vivo; `infrastructure/webhooks/webhook_processor.py` sin uso); dos senders; `/api/notify` y `/api/notify/v2` (`main.py:182-197`); `sys.path` en `erp/bridge.py:62-63,172-173`, `messaging/sender.py:142-143`, `service_host.py:40-41`; respaldo SQLite bloqueado solo si `is_production()` (`erp/bridge.py:213-218`) | `tests/architecture/test_whatsapp_runtime_imports.py` (falla) | WA-016, WA-019, WA-050, WA-002 |
| §3 | Leer los skills | — | no verificable en código | — | — |
| §4 | Seis entregables de auditoría y clasificación REUSE…BLOCKED | parcial | existen los seis en `docs/refactor/whatsapp_*.md`, pero describen archivos borrados (p. ej. `whatsapp_legacy_inventory.md`: 25 referencias a `core/`, 6 a `services/whatsapp_service`) | — | WA-051; esta matriz cumple el papel de inventario vigente |

## §5–§8 Contextos, arquitectura objetivo, main y composición

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §5 | Dueños: Orders, Quotes, Payments, Customers, Loyalty | defectuoso | pedidos como `ventas` `pendiente_wa` (`erp/bridge.py:474-501`), que la migración `255_sales_legacy_backfill.py:17-22` declara «no son ventas»; cotizaciones en tabla legacy `cotizaciones`; anticipos legacy; clientes en `clientes` | — | WA-003, WA-021, WA-028, WA-004, WA-034 |
| §6 | Estructura `bootstrap/domain/application/infrastructure/api/conversations` | parcial | existe salvo `api/` y `conversations/`; conviven `flows/`, `router/`, `parser/`, `state/`, `erp/`, `messaging/` legacy | — | WA-050 |
| §7 | `main.py` mínimo con `ApplicationFactory` | defectuoso | `main.py:24-28,33-79,95-96,110-113,116-165,174-227`; `bootstrap/application_factory.py:7-17` («todavía NO es el entrypoint») | `whatsapp_service/tests/test_application_factory.py` (factory aislada) | WA-016, WA-007 |
| §8 | `CompositionRoot` sin globals ni contenedor expuesto | parcial | `bootstrap/composition_root.py:199-245` arma 41 servicios; no arma autenticador de webhook, repositorio de plantillas ni de agentes (`:20-24`); cada servicio recibe `root` completo; globals en `webhook/whatsapp.py:21-31`, `webhook/mercadopago.py:17-24`, `config/settings.py:63`, `middleware/service_auth.py:54` | `test_composition_root.py`, `test_lifecycle.py` | WA-016 |

## §9–§16 Identificadores, cuentas, números, identidad, teléfono, conversación, mensajes, privacidad

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §9 | UUIDv7 en todos los ids; sin AUTOINCREMENT ni `lastrowid` | parcial | canon con `new_uuid` (`domain/whatsapp/_ids.py:2`); ofensores: `uuid4` de respaldo `erp/bridge.py:67-69`; `lastrowid` sobre PK TEXT `erp/bridge.py:492,706,771,1004`, `erp/gateways/payment_gateway.py:29`; DDL INTEGER en ejecución `erp/pos_notifier.py:230`, `state/reminder_engine.py:81`; INSERT sin `id` `erp/pos_notifier.py:270-279`, `erp/adjustment_approval.py:127,137` | `tests/test_whatsapp_schema.py::test_every_table_has_text_primary_key`; `whatsapp_service/tests/test_wa_event_log_insert.py` (2 fallan) | WA-014, WA-005, WA-007 |
| §10 | Cuentas y números con rol de canal y estado | parcial | entidades y tablas canónicas (`domain/whatsapp/entities/channel_number.py:20-75`; `whatsapp_schema.py:77,102`) sin uso vivo; vivo lee `whatsapp_numeros` legacy con dos DDL (`m000_base_schema.py:2686`, `042_whatsapp_multicanal.py:28`) y tokens en claro (`m000:2692`); nada da de alta `whatsapp_channel_numbers` | `test_domain_whatsapp_numbers`, `test_sqlite_whatsapp_repositories::TestNumberRepository` | WA-013, WA-043, WA-008 |
| §11 | Enrutamiento multi-número sin sucursal Principal | defectuoso | sin políticas de enrutamiento; `ctx.sucursal_id or 1` en `flows/pedido_flow.py:270,279,301`, `router/message_router.py:144-145`, `flows/registro_flow.py:85` y 6 archivos más; salida por un solo número `messaging/sender.py:44-50`; buscador global con sucursal vacía `main.py:131` | `test_message_router_branch_switch.py` (1 falla) | WA-013 |
| §12 | `WhatsAppIdentity`, teléfono no es PK | defectuoso | vivo: `conversations.phone TEXT PRIMARY KEY` (`migrations/whatsapp_runtime.py:46`); cliente por `LIKE '%sufijo' LIMIT 1` sin orden (`erp/bridge.py:291-295`); canon sin uso (`whatsapp_schema.py:119`) | `tests/test_wa_bridge.py::test_finds_by_last_10_digits` (no se recolecta) | WA-012 |
| §13 | Un solo normalizador E.164 | duplicado | núcleo `whatsapp_service/phone_number.py:5-40` con defecto `521…`→`+521…` (`:30-31`); recorte suelto `webhook/mercadopago.py:121`; en el ERP 2 validadores E.164 (`backend/domain/customers/value_objects/phone_number.py:12-24`, `backend/domain/hr/value_objects.py:12-25`), 3 regex en línea y 3 políticas de duplicados con `re.sub(r"\D")` | `test_domain_whatsapp_numbers::TestWhatsAppPhoneNumber` (sin caso `521`) | WA-012 |
| §14 | Conversación, sesión y contexto versionado (12 estados) | defectuoso | vivo en `conversations.db` aparte (`config/settings.py:141`), estados `FlowState` legacy (`models/context.py:16-40`), JSON sin versión que se pierde en silencio (`state/conversation.py:65-79`), timeout silencioso (`:44-55`); canon sin uso (`domain/whatsapp/enums.py:52-64`) | `test_conversation_state_machine.py` (canon) | WA-022 |
| §15 | Mensajes y entregas con estados y webhooks de estado | defectuoso | vivo `message_log` solo entrantes (`migrations/whatsapp_runtime.py:50`); salientes no se registran (`messaging/sender.py:165-205`); estados de Meta descartados (`webhook/whatsapp.py:98-103`); solo el primer mensaje del lote (`models/message.py:52-63`) | `test_domain_whatsapp_message` (canon) | WA-006, WA-018, WA-027 |
| §16 | Retención y datos sensibles | ausente | sin políticas ni purga; contenido en claro (`state/conversation.py:125`); `ai_intent_log` con vista previa y hash sin sal (`ai/audit_log.py:16-27`); teléfonos completos en logs (7 sitios) | `test_redaction.py` (solo función) | WA-011 |

## §17–§23 Webhook, seguridad, idempotencia, procesamiento, inbox/outbox, gateway, secretos

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §17 | Un solo webhook `GET/POST /webhooks/whatsapp`, sin negocio, 200 rápido | defectuoso | rutas vivas `/webhook`, `/webhook/mercadopago`, `/api/notify/*` ×4, `/api/notify/v2/*` ×4, `/api/delivery/orders/*` ×2, `/diagnostics`, `/health`, `/`; procesa en línea con Ollama, Graph y ERP (`webhook/whatsapp.py:134-141`); excepción → 200 | `tests/test_wa_phase9_regression.py`; `test_webhook_production_fail_closed.py` | WA-019, WA-006 |
| §18 | Firma, timestamp, replay, hash, id del evento, intentos inválidos registrados | parcial | firma correcta (`middleware/hmac_validator.py:9-14`); sin firma si falta `APP_ENV` (`config/settings.py:166`, SDLC-WA-002 en spec aprobado, `plan.md` borrador); sin timestamp para Meta (`webhook/whatsapp.py:91-95`); intentos inválidos solo en log (`:73`) | `test_webhook_invalid_signature_returns_403`; `test_mercadopago_webhook_signature.py` (1 falla) | WA-002, WA-010 |
| §19 | Idempotencia técnica y de negocio separadas | defectuoso | técnica: check-then-insert no atómico (`state/conversation.py:118-135`), marca antes de procesar; negocio vivo en `wa_business_idempotency` legacy (`migrations/whatsapp_runtime.py:32`): pedido con `suc or 1` en la clave, **cotización sin clave**, pago por `venta:monto` (`webhook/mercadopago.py:145`); canon `BusinessOperationIdempotencyRecord` sin uso vivo | `TestSqliteWhatsAppIdempotencyRepository` (canon) | WA-006, WA-001, WA-028 |
| §20 | Webhook persiste, inbox, worker procesa | parcial | `WebhookProcessor` (`infrastructure/webhooks/webhook_processor.py:75-126`) e `InboxWorker` (`inbox_worker.py:11-14,32-36`, manejador no-op) sin llamadores; lifespan no lanza tareas (`main.py:84-170`) | `test_webhook_processor.py`, `test_inbox_worker.py` (unitarias) | WA-006, WA-019 |
| §21 | Inbox y outbox; salida crítica persistida antes | parcial | `whatsapp_inbox`/`whatsapp_outbox` canon sin tráfico; `whatsapp_queue` y `wa_reminder_queue` huérfanas; `product_whatsapp_outbox` duplicado (la única que se drena); confirmaciones de pedido y pago salen sin persistir | `test_outbound_dispatcher.py`, `test_sqlite_outbox_repository.py` | WA-018, WA-014, WA-039 |
| §22 | Un solo `WhatsAppProviderGateway` | duplicado | gateway Meta (`infrastructure/providers/meta_cloud_api/gateway.py:32-220`) usado solo por `/health` y v2; 29 archivos llaman `messaging/sender.py` directo; `get_message_status` siempre None (`:134-144`); httpx directo a Mercado Pago (`flows/pago_flow.py:79-117`) | `test_meta_cloud_api_gateway.py` | WA-018 |
| §23 | Todos los secretos en `SecretStoreGateway`, nunca en SQLite en claro | parcial | 6 secretos por `SecretStore` (`config/settings.py:77-119`); `MP_ACCESS_TOKEN` y `ERP_API_KEY` solo de entorno (`:132`; `erp/bridge.py:149`); respaldo `configuraciones.wa_*` en claro (`backend/infrastructure/integrations/whatsapp_credential_resolver.py:55-58`); sin `masked_value`/`last_rotated_at`; sin tokens en código | `test_secret_store.py`; `tests/integration/configuracion/test_whatsapp_credentials_regression.py` | WA-008, WA-038 |

## §24–§32 Plantillas, motor conversacional, intenciones, IA y contexto

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §24 | Plantillas del proveedor versionadas (categoría, estado, esquema) | documentado no implementado | diccionario de 9 entradas (`messaging/templates.py:15-61`); repositorio «futuro» (`bootstrap/composition_root.py:23`); catálogo de plantillas del ERP (`backend/domain/notifications/entities/notification_template.py:29-37`) no consumido | `test_templates_parameter_validation.py` | WA-024 |
| §25 | `ConversationResponseTemplate` versionable y localizable | ausente | ~170 textos fijos; «Vigencia: 7 días» en `router/notify_router.py:89` y `application/notification_service.py:56` | ninguna | WA-025 |
| §26 | `ConversationEngine` + máquina de estados, no if/elif | duplicado | canon sin uso (`application/conversation_engine.py:37-96`); vivo if/elif (`router/message_router.py:137-155`; `flows/pedido_flow.py:36-63,179-353`); código muerto (`delivery_flow.py`, menú secundario, horarios/orquestador/recordatorios no inyectados) | `test_conversation_engine.py` (canon); `test_conversation_quote_context.py` (falla) | WA-022 |
| §27 | Catálogo de 25 intenciones | duplicado | 25 en el enum canon (`domain/whatsapp/enums.py:121-151`); vivo con 4 vocabularios; 11 ausentes en vivo (CHECK_PRICE, CHECK_STOCK, UPDATE_ORDER, TRACK_DELIVERY, UPDATE_ADDRESS, CHECK_LOYALTY, SHOW_DIGITAL_CARD, CHECK_COUPON, HUMAN_HANDOFF, OPT_OUT, SEARCH_PRODUCT fuera del pedido) | `test_intent_resolution_value_objects.py` (canon) | WA-023 |
| §28 | Resolución por capas en orden | parcial | canon en orden correcto (`application/intent_resolution_service.py:92-143`) sin uso; vivo pone la IA antes que las capas deterministas (`ai/intent_resolver.py:49-110`), sin capa de estado esperado ni handoff final | `test_intent_resolution_service.py`; `test_intent_resolver_ai_paths.py` (5 fallan) | WA-023 |
| §29 | `IntentAIProvider`; la IA no ejecuta negocio | parcial | puerto solo con `NullIntentAIProvider`; IA «en la nube» simulada por palabras (`ai/intent_ai_client.py:53-64`); Ollama sin validar (`parser/intent_parser.py:138-162`); IA fija `delivery_type`/`scheduled_at` (`router/message_router.py:345-353`); la IA no crea ventas directamente; escribe `configuraciones` en cada mensaje (`ai/intent_resolver.py:36-47`) | `test_intent_resolver.py` (1 falla) | WA-023, WA-007 |
| §30 | `IntentEntity` tipada y validada | parcial | canon con `name` libre (`value_objects/intent_resolution.py:32-44`); vivo con dicts; `int(prod["id"])` contra UUIDv7 (`router/message_router.py:337`, `ai/intent_resolver.py:136`, `flows/pedido_flow.py:100`) | ids enteros en `tests/test_wa_flows.py` | WA-020, WA-023 |
| §31 | El contexto guarda referencias, no copias maestras | defectuoso | vivo guarda precio, existencia y totales (`models/context.py:43-132`; `flows/pedido_flow.py:104,155`) y el precio cacheado se manda como precio de registro (`application/confirm_order_use_case.py:53-59` → `erp/bridge.py:433-439,470-501`); canon correcto sin uso (`domain/whatsapp/entities/conversation_context.py:16-28`) | `test_domain_whatsapp_conversation.py` (canon) | **WA-021 (P0)**, WA-022 |
| §32 | Menú configurable con listas y botones | parcial | 3 botones fijos (`messaging/interactive.py:12-24`); listas de 10 sin paginar (`:43,61,78`); id de categoría derivado del nombre (`:63`) | `tests/test_wa_flows.py::test_menu_flow_handles_menu_action` | WA-025 |

## §33–§46 Contextos del ERP a través del canal

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §33 | Catálogo vía consultas de Productos/Precios/Disponibilidad | defectuoso | SQL propio (`erp/catalog_sql.py:35-68`; `parser/product_matcher.py:51`); dueños sin API (`backend/application/pricing/queries/product_price_query_service.py`, `orders_delivery/queries/order_capture_catalog_query_service.py`) | `test_catalog_sql_canonical.py` | WA-021, WA-003 |
| §34 | Borrador del canal ≠ pedido; `CreateCustomerOrder` en Orders | defectuoso | vivo escribe `ventas` `pendiente_wa` + `detalles_venta` (`erp/bridge.py:474-501`); `CreateCustomerOrderUseCase` (`order_capture_use_cases.py:36`) sin API; `ERPBridge.create` doble (`erp/bridge.py:395,654`) | `test_order_draft_service.py` (canon con fakes) | WA-003 (ampliado), WA-021, ORD-003 |
| §35 | kg, g, pieza, paquete, caja; peso variable | parcial | sin gramos/paquete/caja (`parser/patterns.py:59-77`); unidad pedida ignorada (`flows/pedido_flow.py:168`) | ninguna | WA-030 |
| §36 | Ajuste de peso por comando idempotente de Orders | defectuoso | UPDATE directo a `delivery_items`/`delivery_orders` (`erp/adjustment_approval.py:80-121`), módulo no importable (`:15-17`), «no acepto» = aceptación (`router/message_router.py:212-214`); dueños `Accept/RejectWeightAdjustmentUseCase` (`catch_weight_use_cases.py:119,146`) exigen permiso de empleado | `test_adjustment_approval_phase7.py` (no se recolecta) | WA-005 (ampliado), WA-029 |
| §37 | Quotes: crear, aceptar, rechazar, convertir | duplicado | tabla legacy `cotizaciones` (`erp/bridge.py:700-715,849-851`); rechazo con UPDATE directo incluso en producción (`flows/cotizacion_flow.py:198`); casos de uso de Quotes sin uso (`backend/application/quotes/use_cases/quote_use_cases.py:129,333,343`) | `test_cotizacion_flow_phase6.py` (falla) | WA-028 |
| §38 | Pagos: link, estado, intención, confirmación por Payments | defectuoso | anticipo calculado en el canal (`application/confirm_order_use_case.py:136-142`; `erp/bridge.py:886`); confirmación con `UPDATE ventas` (`erp/gateways/payment_gateway.py:52-55`) con cualquier monto; link prometido y nunca generado (`flows/pedido_flow.py:319-323`) | `test_payment_service.py` (canon) | WA-001, WA-004 (ampliados), PAY-025 (ampliado), PAY-014 |
| §39 | Webhook de Mercado Pago en Payments, no en WhatsApp | defectuoso | `webhook/mercadopago.py` montado en el microservicio (`main.py:183,190`) | `test_mercadopago_webhook_signature.py` | PAY-010 (enlazado) |
| §40 | Crédito por elegibilidad del contexto Crédito | ausente | el canal calcula `credit_limit - credit_balance` (`erp/bridge.py:358-363`) y decide el anticipo (`:722-729`); `CheckCreditSaleEligibilityUseCase` sin uso | `tests/test_wa_bridge.py::TestGetCreditoDisponible` (no se recolecta) | WA-031 |
| §41 | Delivery por casos de uso de Delivery | defectuoso | `UPDATE ventas` con fecha +1 día (`erp/gateways/delivery_gateway.py:25-30`); `POST /api/delivery/orders/status` siempre NameError (`router/delivery_router.py:23,216`) | `test_delivery_request_service.py` (canon) | WA-032 |
| §42 | Ubicación, dirección guardada, confirmación de mapa | ausente | texto libre ≥5 caracteres (`flows/pedido_flow.py:224-227`); LOCATION declarado sin parsear (`models/message.py:17,74-91`) | ninguna | WA-032 |
| §43 | Lealtad vía consultas de Loyalty | parcial | SQL directo a `loyalty_snapshots` (`infrastructure/erp_clients/loyalty_client.py:34-37`); ningún flujo la ofrece | `test_loyalty_client.py` | WA-033 |
| §44 | Registro con aviso, consentimiento y `CreateCustomer` | defectuoso | alta al primer mensaje (`router/message_router.py:106-119`; `flows/registro_flow.py:75-90`); dos maestros (`erp/bridge.py:174-178,331-333`); `sender.py:147` crea `customers` por envío | `test_bridge_create_cliente_minimo.py` | WA-034, CRM-003 (ampliado) |
| §45 | Consentimiento por categoría | parcial | control solo `WHATSAPP=WITHDRAWN`, falla abierto (`messaging/sender.py:114-158`); `ConsentType` del ERP con MARKETING/PROFILING (`backend/domain/customer_privacy/enums.py:9-17`) | `test_sender_consent_gate.py` | WA-035 |
| §46 | `ProcessWhatsAppOptOutUseCase` | ausente | sin STOP/BAJA en vivo; `ConsentService.record_opt_out` sin llamador y evita `WithdrawConsentUseCase` (`infrastructure/erp_clients/consent_client.py:91-106`) | `test_consent_client.py` | WA-035 |

## §47–§51 Handoff, agentes, bandeja, notificaciones y alertas

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §47 | Handoff con estados y motivos | ausente | «Te comunico con un asesor» (`messaging/interactive.py:174-179`) sin escalar; `HandoffService.escalar` sin llamador; «Responde directamente desde WhatsApp» (`middleware/handoff.py:33`); canon con 4 estados (`domain/whatsapp/enums.py:274-280`) | `test_handoff_service.py` (canon) | WA-036 |
| §48 | `AgentRoutingPolicy` | ausente | sin agentes, colas ni SLA; asignación a teléfono de personal (`whatsapp_schema.py:327`) | ninguna | WA-036 |
| §49 | Bandeja de atención con filtros | ausente | no hay módulo WhatsApp en el escritorio | ninguna | WA-041 |
| §50 | Notificaciones salientes decididas por Notificaciones | parcial | ERP llama `/api/notify` v1 sin outbox (`backend/infrastructure/integrations/whatsapp_client.py:180,184`); v2 sin llamadores; `resolve_route` sin llamadores (`backend/domain/notifications/policies/notification_routing_policy.py:15-19`); cliente de Pedidos sin conexión ignora credenciales de Integraciones (`backend/infrastructure/integrations/orders_delivery_whatsapp_client.py:32`); faltan 7 avisos de la lista | `test_notify_dispatch_router.py` (v2) | WA-037, WA-038, ORD-006 (ampliado) |
| §51 | Alertas internas con severidad y escalamiento | parcial | `notifications/alerts.py:17-87` sin llamadores; sin escalamiento en `backend/` | ninguna | WA-040, INV-008 (enlazado) |

## §52–§61 Contratos internos, eventos, observabilidad y resiliencia

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §52 | `ERPChannelGateway` con clientes por contexto | defectuoso | puertos en `domain/whatsapp/erp_ports.py:86-135` sin Inventory; clientes envuelven `ERPBridge` en proceso; endpoints `/api/v1/*` inexistentes (`backend/api/main.py:23-25`, `central_app.py:152-153`) | `test_erp_bridge_clients.py` (fake oculta `create` doble) | WA-003 (ampliado) |
| §53 | HMAC con timestamp, nonce, rotación | parcial | ERP→WA correcto (`middleware/service_auth.py:57-142`); WA→ERP `X-API-Key` fija (`erp/bridge.py:191-195`); nonces en memoria; sin rotación; `X-Internal-Key` solo en docstrings | `test_service_auth.py` | WA-009 |
| §54 | Identidad de servicio `WHATSAPP_CHANNEL_SERVICE` | ausente | constante sin uso (`middleware/service_auth.py:43`); ninguna identidad en el ERP | ninguna | WA-009 |
| §55 | 19 eventos canónicos del canal, sin duplicados | parcial | 11 de 19 definidos, cero emitidos (`domain/whatsapp/events.py:33-43`); nombres duplicados en `erp/events.py:43-53` | `test_domain_whatsapp_events.py` (solo nombres) | WA-015 |
| §56 | Eventos de negocio solo de sus dueños | defectuoso | SALE_CREATED (`erp/pos_notifier.py:84-86`), PAYMENT_RECEIVED (`webhook/mercadopago.py:151,159`); triple emisión por acción; `wa_event_log` sin lector | `test_pos_notifier_dedupe` (fija la triple emisión) | WA-015 |
| §57 | Correlación y métricas | parcial | sin `correlation_id` en logs (`router/message_router.py:247`); `/diagnostics` cuenta tablas canónicas que el vivo no escribe (`application/diagnostics_service.py:43-55`) | `test_diagnostics_service.py` | WA-046, WA-017 |
| §58 | Health checks completos sin secretos | parcial | `bootstrap/health_checks.py` con 4 estados; ping síncrono a Graph en cada `/health` sin auth (`infrastructure/providers/meta_cloud_api/gateway.py:148-171`; `main.py:201`); `erp_api` solo mira el tipo (`health_checks.py:233-250`) | `test_health_checks.py::test_detail_never_contains_a_secret_value` | WA-017 |
| §59 | Rate limiting por identidad, número, IP, cuenta, plantilla | parcial | solo por teléfono en memoria, 15/min (`middleware/rate_limiter.py:18-39`); lo cortado se descarta | `test_wa_phase9_regression.py::test_webhook_rate_limit_blocks_processing` | WA-039 |
| §60 | Reintentos configurables sin reintentar no reintentables | parcial | `MAX_ATTEMPTS=5`, espera fija sin jitter (`domain/whatsapp/entities/outbox_message.py:31-46`); reintenta `opted_out` (`gateway.py:196-200`) | `test_outbound_dispatcher.py` | WA-039 |
| §61 | `WhatsAppDeadLetter` con resolución | parcial | tabla completa (`whatsapp_schema.py:236-247`) sin escritor; solo la lee `diagnostics_service.py:118` | `test_diagnostics_service.py::test_dead_letter_unresolved_vs_total` | WA-039 |

## §62–§64 Media, archivos y horarios

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §62 | `WhatsAppMediaReference` y pipeline de media | ausente | audio/video/sticker/contactos descartados sin respuesta (`models/message.py:12-20,67,108-109`); `download_media` sin llamadores ni validación (`gateway.py:113-130`) | `TestDownloadMedia::test_two_step_download` (transporte) | WA-027 |
| §63 | Seguridad de archivos | ausente | sin validación de MIME, tamaño, hash ni nombre | ninguna | WA-027 |
| §64 | Locale, zona, horarios, feriados; fuera de horario | parcial | `config/schedules.py:21-72` sin zona, abierto ante error, sin feriados; aviso de cerrado y el flujo sigue (`router/message_router.py:143-147`); política del pedido nunca corre (`flows/pedido_flow.py:355-369`) | ninguna | WA-026 |

## §65–§73 Módulo, interfaz, permisos, segregación, auditoría y errores

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §65 | Módulo global WhatsApp + configuración técnica en Integraciones | parcial | sin módulo (`frontend/desktop/shell/sidebar/migrated_modules_navigation.py:129-231`); Integraciones genérico, definición `WHATSAPP` no sembrada (`frontend/desktop/modules/configuracion/pages/integraciones_page.py:48-433`); token en el almacén de secretos con respaldo en claro | `tests/integration/configuracion/test_whatsapp_credentials_regression.py` | WA-041, WA-043, WA-008 |
| §66 | Navegación interna (18 secciones) | ausente | no existe el módulo | ninguna | WA-041 |
| §67 | Máximo 6 KPI, calculados en backend | ausente | métricas en `/diagnostics` sin interfaz; resumen CRM fija ceros (`backend/application/customers/queries/customer_whatsapp_summary_query.py:60-62`) | `test_crm_13_integraciones.py::TestCustomerWhatsAppSummaryQuery` | WA-041 |
| §68 | Componentes del sistema de diseño (ConversationList, ConversationThread, MessageComposer, AgentBadge, SlaBadge) | ausente | `frontend/desktop/components/` sin componentes de conversación | ninguna | WA-042 |
| §69 | Composer con validaciones | ausente | sin endpoint ni pantalla de respuesta (`whatsapp_service/main.py:189-197`) | ninguna | WA-042 |
| §70 | 37 permisos del canal en backend | ausente | catálogo sin WhatsApp (`backend/application/security/permission_catalog.py:58-88`); solo `CLIENTES.whatsapp.ver` y `<MODULO>.whatsapp.gestionar` de alertas; casos de uso de integraciones sin actor (`backend/application/use_cases/configuracion/integration_management_use_cases.py:63-278`) | ninguna | WA-044, ARQ-PERM-001 (enlazado) |
| §71 | Segregación de funciones | ausente | handoff sin actor ni motivo (`whatsapp_service/application/handoff_service.py:72-78`); dead letter sin `resolved_by` escrito; bloqueo sin causa (`whatsapp_schema.py:127`) | `test_handoff_service.py::test_resolve_marks_request_resolved` | WA-044 |
| §72 | Auditoría del canal con campos de trazabilidad | ausente | ninguna de las 18 tablas es de auditoría (`whatsapp_schema.py:53-72`); `wa_event_log` sin usuario ni antes/después; auditoría de Configuración en el presentador (`configuracion_presenter.py:332`) | ninguna | WA-045, WA-011 |
| §73 | Errores tipados; prohibido `except Exception: pass` | documentado no implementado | 1 de 23 errores (`domain/whatsapp/exceptions.py:42`); 129 `except Exception`, 29 tragan el error | ninguna | WA-047 |

## §74–§81 Eliminación del legacy, tablas, fases, pruebas, guardias, DoD y reporte

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §74 | Eliminación total del legacy con cero consumidores | parcial | borrados: los 3 shims y `core/` (contradice `CLAUDE.md` reglas 8-9); vivos: `ERPBridge` con escrituras, `BusinessOrchestrator` (`erp/business_orchestrator.py:44`), sender legacy (29 consumidores), webhook legacy, `/api/notify` v1, `WAEventEmitter` (`main.py:116-118`), imports `core.*` (`erp/adjustment_approval.py:15-17`, `erp/bridge.py:506,570`, `application/confirm_order_use_case.py:114`) | `test_whatsapp_runtime_imports.py` (falla) | WA-050, WA-005, WA-051 |
| §75 | Una fuente canónica por concepto | duplicado | 3 fuentes de números, 2 de conversaciones, 2 outboxes, colas huérfanas, `pedidos_whatsapp` con lectores fantasma | `test_every_table_has_text_primary_key` | WA-014 |
| §76 | Fases WA-0…22 | — | orden respetado en «Depende de» | — | todos |
| §77 | Pruebas obligatorias (arquitectura, webhook, idempotencia, conversación, pedidos, seguridad, handoff, consentimiento) | parcial | existen muchas unitarias del canon, fuera de CI; las del camino vivo usan esquemas e ids falsos | ver Mediciones | WA-048 |
| §78 | 20 guardias de arquitectura | ausente | 0 de 20 | — | WA-049 |
| §79 | Definición de terminado (≈80 casillas) | parcial | casillas «existe X» cumplidas solo en el canon; casi todas las «no existe legacy X» incumplidas | — | WA-050 |
| §80 | Reporte final y tabla de destino | — | esta matriz cubre los puntos 1–12 (inventario); 13–33 se cumplen al cerrar los ítems | — | WA-050, WA-051 |
| §81 | Regla final | — | resumen de lo anterior | — | — |

## Defectos nuevos encontrados (no estaban en el backlog)

| Defecto | Evidencia | Ítem |
|---|---|---|
| El precio cacheado en la conversación es el precio de registro del pedido | `application/confirm_order_use_case.py:53-59` → `erp/bridge.py:433-439,470-501` | WA-021 |
| Pago aprobado confirma la venta con cualquier monto; dos pagos iguales se fusionan | `erp/gateways/payment_gateway.py:46-55`; `webhook/mercadopago.py:145` | WA-001 (ampliado) |
| «no acepto» se registra como aceptación del ajuste de peso | `router/message_router.py:212-214` | WA-005 (ampliado) |
| `int()` sobre ids UUIDv7 de producto | `router/message_router.py:337`; `ai/intent_resolver.py:136`; `flows/pedido_flow.py:100` | WA-020 |
| `ERPBridge.create` definido dos veces | `erp/bridge.py:395,654` | WA-003 (ampliado) |
| `notification_inbox` y `wa_event_log` insertados sin `id` contra PK TEXT NOT NULL | `erp/pos_notifier.py:266-284`; `erp/adjustment_approval.py:127,137` | WA-005 (ampliado) |
| Rechazo de cotización escribe la base del ERP en producción | `flows/cotizacion_flow.py:198` | WA-028 |
| `POST /api/delivery/orders/status` siempre falla (import comentado) | `router/delivery_router.py:23,216` | WA-032 |
| Cliente de Pedidos ignora credenciales de Integraciones | `backend/infrastructure/integrations/orders_delivery_whatsapp_client.py:32` | WA-038 |
| Buscador de productos global con sucursal vacía | `main.py:131` | WA-013 |
| Solo se procesa el primer mensaje de cada lote | `models/message.py:52-63` | WA-006 (ampliado) |
