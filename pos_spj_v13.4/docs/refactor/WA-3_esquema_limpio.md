# WA-3 — Esquema limpio (canal WhatsApp)

Ejecutado: 2026-09-01. Migración `243_whatsapp_bounded_context_schema`
(`backend/infrastructure/db/schema/whatsapp_schema.py::create_whatsapp_schema`)
— born-clean UUIDv7 para las 8 entidades de WA-2 más las 4 capacidades de
infraestructura transversal que el prompt maestro exige para el canal:
inbox único, outbox único, idempotencia de negocio, dead letter.

Sigue el mismo molde ya usado por `orders_delivery_schema.py` (migración
226) y `loyalty_schema.py` (migración 225): un módulo de esquema dedicado
con `_DDL`/`_INDEXES`/`create_X_schema()`/`drop_X_schema()`, invocado desde
una migración delgada que solo delega y hace `commit()`.

---

## 1. Las 12 tablas

| Tabla | Entidad WA-2 que respalda |
|---|---|
| `whatsapp_business_accounts` | `WhatsAppBusinessAccount` |
| `whatsapp_provider_configurations` | `WhatsAppProviderConfiguration` |
| `whatsapp_channel_numbers` | `WhatsAppChannelNumber` |
| `whatsapp_identities` | `WhatsAppIdentity` |
| `whatsapp_conversations` | `WhatsAppConversation` (+ `context_json`/`context_version` para `ConversationContext`) |
| `whatsapp_conversation_sessions` | `ConversationSession` |
| `whatsapp_messages` | `WhatsAppMessage` |
| `whatsapp_message_deliveries` | `WhatsAppMessageDelivery` |
| `whatsapp_inbox` | InboundMessageJob (§20-21, sin entidad de dominio propia todavía — WA-6) |
| `whatsapp_outbox` | Outbox de envío (§21-22) |
| `whatsapp_business_operation_idempotency` | BusinessOperationIdempotencyRecord (§19) |
| `whatsapp_dead_letter` | WhatsAppDeadLetter (§61) |

Cada columna de cada tabla es exactamente el campo correspondiente de la
entidad de dominio de WA-2, sin adaptar nada — verificado con un test de
round-trip real (`TestDomainEntityRoundTrip` en
`whatsapp_service/tests/test_whatsapp_schema.py`) que construye una
entidad vía su `create()`/`transition_to()` del dominio e inserta sus
campos directamente contra el esquema.

## 2. UUIDv7 (REGLA CERO)

Los 12 `PRIMARY KEY` son `TEXT`, ninguno `INTEGER AUTOINCREMENT` —
verificado por test parametrizado sobre las 12 tablas
(`test_every_table_has_text_primary_key`). Ningún `DEFAULT` SQL genera el
id — siempre lo provee el dominio (`domain/whatsapp/_ids.py::new_id()`,
WA-2) antes del insert, mismo criterio que el resto del esquema born-clean
del repo.

## 3. Constraints

- `whatsapp_business_accounts.business_account_external_id UNIQUE`
- `whatsapp_provider_configurations.account_id UNIQUE` (una config por cuenta)
- `whatsapp_channel_numbers.phone_number_external_id UNIQUE`
- `whatsapp_identities.wa_id UNIQUE`
- `whatsapp_messages.provider_message_id UNIQUE` (cuando no es NULL —
  idempotencia técnica de mensaje por `message_id` de Meta, §19)
- `whatsapp_message_deliveries.message_id UNIQUE` (una entrega por mensaje)
- `whatsapp_inbox.message_id UNIQUE` (un job de inbox por mensaje)
- `whatsapp_outbox.operation_id UNIQUE` (cuando no es NULL)
- `whatsapp_business_operation_idempotency.operation_id UNIQUE` **y**
  `.fingerprint UNIQUE` — el segundo es la clave de dedup real de §19
  ("dos mensajes distintos, misma acción de negocio"), verificado con test
  de que un `fingerprint` repetido con `operation_id` distinto también
  falla, no solo el caso obvio de `operation_id` repetido.
- `REFERENCES` (documental — SQLite no las aplica salvo
  `PRAGMA foreign_keys=ON`, mismo criterio que `orders_delivery_schema.py`)
  encadenando number→account, conversation→identity/number, session/
  message→conversation, delivery/inbox→message.

Estados (`status`/`state`/`identity_status`/`channel_role`/...) **no**
llevan `CHECK` de SQL — el dominio (`domain/whatsapp/enums.py` + entidades,
WA-2) es la única fuente de verdad de valores y transiciones válidas, igual
que `sales_schema.py`/`loyalty_schema.py`/`orders_delivery_schema.py`.

## 4. Inbox (§20-21)

`whatsapp_inbox`: `message_id` (único), `status`
(PENDING/PROCESSING/COMPLETED/FAILED/RETRY/DEAD_LETTER — vocabulario de
§21, aún no está en `domain/whatsapp/enums.py` porque ningún entity de WA-2
lo modela todavía; se agrega el `MessageDeliveryStatus`-equivalente para
Inbox cuando WA-6 construya el webhook/worker real), `attempts`,
`last_error`, `locked_at` (para que un worker reclame un job sin
condiciones de carrera — mecanismo, no política; la política de qué worker
gana es WA-6), `processed_at`.

## 5. Outbox (§21-22) — cierra un hueco real, no solo "limpieza de esquema"

La auditoría WA-0 (`whatsapp_schema_consolidation.md` §2) encontró que el
microservicio oficial **no tiene ningún outbox persistido** — envía
síncrono dentro del propio request HTTP (`messaging/sender.py`); si
`httpx` falla, el mensaje simplemente no sale, sin reintento ni registro
previo. El único outbox real del sistema hoy es el legacy `whatsapp_queue`,
que usa exclusivamente el pipeline legacy (`core/services/whatsapp_service.py`),
no el microservicio nuevo. `whatsapp_outbox` (esta migración) es la
capacidad que cierra ese hueco — pero **todavía no está conectada a nada**:
ni `messaging/sender.py` escribe en ella antes de enviar, ni existe un
worker que la drene. Esa integración es WA-17 (Outbound Messaging).

## 6. Idempotencia de negocio (§19)

`whatsapp_business_operation_idempotency` es deliberadamente más ancha que
la tabla legacy equivalente (`wa_business_idempotency`, creada en código —
no en una migración — con `id INTEGER PRIMARY KEY AUTOINCREMENT` y solo
`action_key`/`result_json`/`status`/`error`): agrega `operation_type`,
`aggregate_type`, `aggregate_id` como columnas propias (no empaquetadas
dentro de un `action_key` compuesto por string, como hace hoy
`BusinessIdempotencyService`), exactamente la forma que pide §19. No
reemplaza `wa_business_idempotency` — sus consumidores reales
(`pedido_flow.py`, `cotizacion_flow.py`, `webhook/mercadopago.py`,
`business_orchestrator.py`) siguen escribiendo ahí sin cambios. Migrar esos
consumidores a la tabla nueva es trabajo de una fase de aplicación
posterior (probablemente WA-9/WA-10), no de esquema.

## 7. Dead letter (§61)

`whatsapp_dead_letter`: registro append-only de fallos definitivos —
`message_id`, `operation_id`, `failure_type`, `attempts`, `last_error`,
`payload_reference`, y el ciclo de resolución manual
(`resolved_at`/`resolved_by`/`resolution`) que §61 pide explícitamente
("no perder mensajes fallidos"). Sin productor todavía — se conecta cuando
WA-17 (reintentos con backoff) decide que un mensaje agotó sus intentos.

## 8. Sin colisión con ninguna tabla legacy

Verificado por test (`TestNoCollisionWithLegacyTables`) contra los 15
nombres de tabla legacy conocidos del inventario WA-0
(`whatsapp_numeros`, `wa_event_log`, `wa_business_idempotency`,
`wa_reminder_queue`, `whatsapp_queue`, `wa_message_queue`, `bot_sessions`,
`bot_mensajes_log`, `rasa_sessions`, `pedidos_whatsapp`,
`pedidos_whatsapp_items`, `conversations`, `message_log`,
`marketing_messages`, `notification_inbox`) y confirmado además con un
bootstrap real de base de datos desde cero
(`scripts/bootstrap_db.py`): tras la migración 243, `whatsapp_numeros` y
`whatsapp_queue` (legacy) y las 12 tablas nuevas coexisten sin conflicto —
14 tablas `whatsapp_*` en total.

**Ninguna tabla legacy se tocó, alteró ni eliminó.** Esta fase solo agrega
el esquema nuevo; la consolidación real (decidir qué pasa con
`pedidos_whatsapp*`/`whatsapp_queue`/`wa_business_idempotency`) sigue
bloqueada por la misma decisión de producto pendiente desde WA-0 (cuál de
las tres pipelines de pedidos es la autoritativa).

---

## Tests

`whatsapp_service/tests/test_whatsapp_schema.py` — 27 tests, todos en
verde: creación de las 12 tablas + idempotencia de `CREATE TABLE IF NOT
EXISTS`, PK `TEXT` en las 12 (parametrizado), `drop_whatsapp_schema`
completo, cero colisión con nombres legacy, constraints `UNIQUE` (incluida
la doble unicidad `operation_id`/`fingerprint` de idempotencia y el caso
`NULL` múltiple permitido en `whatsapp_outbox.operation_id`), 3 tests de
round-trip real dominio→esquema (cuenta, número con teléfono normalizado,
conversación+mensaje+entrega con transición de estado), y 2 tests de que
la migración 243 delega correctamente y está registrada al final de
`migrations.engine.MIGRATIONS`.

- Suite completa `whatsapp_service/tests/`: **217 passed, 11 failed** — los
  11 son los mismos fallos preexistentes y no relacionados ya documentados
  en WA-1/WA-2.
- **Bootstrap real desde cero** (`python scripts/bootstrap_db.py --db
  <temp>.db`): las 243 migraciones corren en orden, la 243 se ejecuta
  correctamente ("whatsapp bounded-context schema ensured"), y las 12
  tablas nuevas quedan verificadas en el archivo `.db` resultante junto a
  las 2 tablas legacy `whatsapp_*` preexistentes (14 en total). Los 3
  fallos de migraciones no relacionadas que el bootstrap reporta (024, 029,
  080) son preexistentes al proyecto — no involucran ninguna tabla ni
  módulo de WhatsApp.
- Sintaxis global: sin errores.

## Siguiente fase

WA-4 — Bootstrap: `ApplicationFactory`, `CompositionRoot`, `lifespan`,
`health checks` — la primera fase que realmente conecta algo de WA-2/WA-3 a
`main.py`. Hasta ahora, dominio y esquema existen pero nada los usa
todavía; eso es deliberado (mismo orden que el resto de los bounded
contexts de este repo: dominio → esquema → bootstrap → casos de uso).
