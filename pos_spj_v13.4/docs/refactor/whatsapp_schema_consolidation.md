# Consolidación de esquema — Canal WhatsApp (FASE CERO — Auditoría)

Cada tabla relacionada con WhatsApp, su dueño real (migración o `CREATE TABLE IF NOT EXISTS` en
código), sus consumidores, tipo de PK actual, y clasificación hacia el conjunto canónico único que
pide el prompt maestro (conversaciones, mensajes, entregas, inbox, outbox, idempotencia, handoff,
cuentas, números, templates, auditoría).

**Regla del proyecto**: identidad UUIDv7-only ("REGLA CERO", citada en varios comentarios del propio
código auditado). Se marca explícitamente cada tabla cuyo PK es `INTEGER PRIMARY KEY AUTOINCREMENT`
como brecha.

---

## 0. Hallazgo crítico — `wa_event_log` tiene DOS definiciones de esquema incompatibles, y la tabla de audit trail no recibe escrituras en producción

Tres lugares distintos del código hacen `CREATE TABLE IF NOT EXISTS wa_event_log` con **columnas de
PK incompatibles**:

| Definidor | PK definida | Archivo:línea |
|---|---|---|
| Migración ERP (autoridad — corre primero, ver `whatsapp_service/main.py:76-84`) | `id TEXT NOT NULL PRIMARY KEY` | `pos_spj_v13.4/migrations/standalone/050_wa_integration.py:43-51` |
| `WAEventEmitter.ensure_tables()` | `id INTEGER PRIMARY KEY AUTOINCREMENT` | `whatsapp_service/erp/events.py:144-152` |
| `POSNotifier._insert_wa_event()` | `id INTEGER PRIMARY KEY AUTOINCREMENT` | `whatsapp_service/erp/pos_notifier.py:165-173` |

Como `CREATE TABLE IF NOT EXISTS` es un no-op si la tabla ya existe, y el orden de arranque real del
microservicio (`whatsapp_service/main.py:76-93`) es: (1) correr las migraciones del ERP —que incluyen
la 050, creando la tabla con `id TEXT NOT NULL PRIMARY KEY`— y **luego** (2) instanciar `WAEventEmitter`
y llamar `ensure_tables()` (que es un no-op porque la tabla ya existe), el esquema que efectivamente
queda en disco en cualquier despliegue normal es el de la migración: **`id TEXT NOT NULL PRIMARY KEY`,
sin default**.

Pero los tres `INSERT INTO wa_event_log` del árbol WhatsApp omiten la columna `id`:

```python
# erp/events.py:118-122 (WAEventEmitter.emit)
self.db.execute("""
    INSERT INTO wa_event_log (event_type, data_json, sucursal_id, prioridad, timestamp)
    VALUES (?, ?, ?, ?, datetime('now'))
""", (event_type, data_json, sucursal_id, prioridad))
```

```python
# erp/pos_notifier.py:174-182 (POSNotifier._insert_wa_event)
self.db.execute("""
    INSERT INTO wa_event_log (event_type, data_json, sucursal_id, prioridad, timestamp)
    VALUES (?, ?, ?, ?, datetime('now'))
""", (event_type, ..., sucursal_id, prioridad))
```

```python
# erp/adjustment_approval.py:123-133 (dos INSERT)
INSERT INTO wa_event_log(event_type, data_json, sucursal_id, prioridad, timestamp) SELECT ?, ...
```

Con `id TEXT NOT NULL PRIMARY KEY` y ninguna cláusula `DEFAULT`, SQLite intenta insertar `NULL` en la
columna omitida y **rechaza la fila con `IntegrityError: NOT NULL constraint failed: wa_event_log.id`**.
Los tres sitios envuelven el `INSERT` en `try/except`:

- `erp/events.py:127-128` — `except Exception: pass` (silencioso total, ni siquiera `debug`).
- `erp/pos_notifier.py:184-185` — `except Exception as exc: logger.debug(...)` (invisible con
  `LOG_LEVEL=INFO`, el default de `config/settings.py:142`).
- `erp/adjustment_approval.py:144-145` — `except Exception as exc: logger.warning(...)` (éste sí es
  visible por defecto).

**Conclusión**: en un despliegue donde las migraciones del ERP corrieron antes de que el microservicio
insertara su primer evento (que es el orden documentado y esperado, `main.py:76-93`), **la tabla
`wa_event_log` nunca recibe filas desde `WAEventEmitter.emit()` ni desde `POSNotifier`** — solo los dos
`INSERT` de `adjustment_approval.py` fallarían de forma visible (`logger.warning`), el resto falla
en silencio. Esto contradice directamente la premisa con la que el propio proyecto describe esta
tabla ("trazabilidad de eventos WA", comentario en `migrations/standalone/050_wa_integration.py:5`) y
la regla 12 del CLAUDE.md del proyecto sobre trazabilidad de operaciones. **Es el hallazgo técnico
individual de mayor severidad de toda esta auditoría**: no es una brecha de arquitectura a futuro, es
un bug de producción activo hoy que rompe silenciosamente el audit trail del canal.

Nota: no se verificó en esta fase si existe algún despliegue donde el orden se invierte (microservicio
arranca antes de que la migración 050 haya corrido alguna vez, dejando la tabla con el esquema
`INTEGER AUTOINCREMENT` en su lugar) — en ese escenario los `INSERT` sí funcionarían. Dado que
`main.py:76-84` ejecuta las migraciones del ERP explícitamente en cada arranque del microservicio
(`run_migrations(mig_conn)`), y la migración 050 está registrada en `migrations/engine.py:48`, ese
escenario alternativo requeriría que la migración 050 fallara silenciosamente antes de crear la tabla
— posible pero no confirmado; se marca como **"requiere verificación"** el caso exacto de cada
despliegue, aunque el camino documentado y esperado es el que produce el bug.

---

## 1. Conversaciones y mensajes

| Tabla | Dueño (creador) | PK | UUIDv7-compatible | Consumidores | Clasificación |
|---|---|---|---|---|---|
| `conversations` | `whatsapp_service/state/conversation.py:33-43` (`CREATE TABLE IF NOT EXISTS`, código, no migración) | `phone TEXT PRIMARY KEY` | Sí (no es un id autogenerado, es la clave natural del teléfono — aceptable) | `ConversationStore`, `WhatsAppMetricsRepository._context_db_metrics` | REUSE — mover la definición a una migración formal en vez de `CREATE TABLE` en código de aplicación |
| `message_log` | ídem, `state/conversation.py:44-51` | `id INTEGER PRIMARY KEY AUTOINCREMENT` | **No** | `ConversationStore.log_message`/`is_duplicate`, `WhatsAppMetricsRepository` | **ALTER** — migrar a `id TEXT PRIMARY KEY` (UUIDv7) |
| `bot_sessions` | `migrations/m000_base_schema.py:1132-1137` | `numero TEXT PRIMARY KEY` | Sí (clave natural) | pipeline legacy (Rasa/`bot_pedidos.py`), `WhatsAppMetricsRepository._legacy_fill` | REUSE si el pipeline legacy se mantiene; **DROP** si se decide retirar Rasa (ver inventario legacy §0) |
| `rasa_sessions` | `migrations/standalone/036_whatsapp_rasa.py:38-48` | `id TEXT PRIMARY KEY` | Sí | Rasa (no confirmado consumidor Python directo en este árbol) | Depende de decisión sobre Rasa — **BLOCKED**, ver inventario legacy |
| `wa_message_queue` | **Ninguno** — no existe ningún `CREATE TABLE` para este nombre en todo `migrations/` (confirmado por grep) | N/A — tabla fantasma | N/A | `WhatsAppHistoryRepository._query_wa_queue`, `WhatsAppMetricsRepository._queue_metrics` (ambos con `try/except` que degradan silenciosamente al fallar) | **DROP la referencia** (no la tabla, porque no existe) — o, si la intención original era que fuera un alias/vista sobre `whatsapp_queue`, crearla explícitamente. Tal como está, es una referencia muerta que dos repositorios de producción consultan sin que nadie note que siempre falla. |

---

## 2. Cola de envío / outbox

| Tabla | Dueño | PK | UUIDv7-compatible | Consumidores | Clasificación |
|---|---|---|---|---|---|
| `whatsapp_queue` | `migrations/m000_base_schema.py:1139-1150` (base) + `migrations/standalone/036_whatsapp_rasa.py:22-36` (`CREATE TABLE IF NOT EXISTS` redundante) + `081_wa_queue_backoff.py` (agrega `proxima_revision`) | `id TEXT NOT NULL PRIMARY KEY` | Sí | `core/services/whatsapp_service.py:MessageQueue` (único consumidor real — es la cola del servicio **legacy**) | **MERGE** con un outbox único del microservicio nuevo — hoy es exclusivamente la cola del camino legacy (§2b de runtime map), el microservicio oficial no tiene tabla de outbox propia (envía síncrono dentro del request, ver runtime map §1) |
| `wa_reminder_queue` | `migrations/standalone/050_wa_integration.py:58-75` | `id TEXT NOT NULL PRIMARY KEY` | Sí | `whatsapp_service/state/reminder_engine.py` (no releído en detalle, pero es el nombre que coincide con su dominio: recordatorios programados) | REUSE — candidato natural a "outbox" de recordatorios en el diseño nuevo |
| `links_pago` | `migrations/m000_base_schema.py:1153-1160` | `pedido_id TEXT NOT NULL PRIMARY KEY` | Sí | No confirmado consumidor directo en el árbol `whatsapp_service/` auditado (el flujo de pago nuevo genera el link on-the-fly vía API de MercadoPago sin persistirlo, `flows/pago_flow.py:72-121`) — **requiere verificación** de si esta tabla la sigue usando el pipeline legacy | Requiere verificación |

**No existe una tabla "outbox" en el sentido estricto para el microservicio oficial** (mensajes
salientes generados por eventos de negocio, con reintentos e idempotencia técnica) — el envío
síncrono (`messaging/sender.py`) no persiste el intento antes de mandarlo; si `httpx` falla, el
mensaje simplemente no sale y solo queda un log de error (`sender.py:216-218`). El único outbox real
del sistema es el legacy `whatsapp_queue` + `MessageQueue`, que **no** lo usa el microservicio nuevo.
Esta es una brecha respecto al requisito del prompt maestro de "single webhook/sender/inbox/outbox".

---

## 3. Idempotencia

| Tabla | Dueño | PK | UUIDv7-compatible | Consumidores | Clasificación |
|---|---|---|---|---|---|
| `wa_business_idempotency` | `whatsapp_service/state/business_idempotency.py:35-47` (`CREATE TABLE IF NOT EXISTS` en código, no migración) | `id INTEGER PRIMARY KEY AUTOINCREMENT` (`action_key TEXT UNIQUE NOT NULL` es la clave funcional real) | **No** el PK, pero sí la clave de negocio (`action_key`) | `BusinessIdempotencyService` (usado por `pedido_flow.py`, `cotizacion_flow.py`, `webhook/mercadopago.py`, `business_orchestrator.py`) | **ALTER** — mover a migración formal + PK `TEXT` (UUIDv7), aunque el campo relevante para deduplicar (`action_key UNIQUE`) ya es correcto y no necesita cambiar |

Idempotencia técnica de mensaje (dedupe por `message_id` de Meta) vive en `message_log` (§1), no en
una tabla separada — está acoplada al log de mensajes en vez de ser un concepto de idempotencia
independiente. En el diseño nuevo debería separarse: `message_log` como historial, una tabla de
idempotencia técnica explícita (o un índice único sobre `message_id`, que ya existe:
`UNIQUE` en `message_id`, `migrations/m000_base_schema.py`, confirmado en el `CREATE TABLE` de
`message_log` visto en `state/conversation.py:46`).

---

## 4. Inbox / notificaciones

| Tabla | Dueño | PK | UUIDv7-compatible | Consumidores | Clasificación |
|---|---|---|---|---|---|
| `notification_inbox` | `migrations/m000_base_schema.py:2775` + `migrations/standalone/041_notification_inbox.py:10` (dos `CREATE TABLE IF NOT EXISTS` — redundante, no conflictivo si tienen el mismo esquema; **no se comparó columna por columna en esta fase, requiere verificación de que ambas definiciones coinciden**) | `id INTEGER PRIMARY KEY AUTOINCREMENT` | **No** | `POSNotifier` (WA→ERP desktop), `WhatsAppNotificationHandler`/`NotificationDispatcher` (eventos ERP→staff) | **ALTER** — PK no UUIDv7; es la tabla de "inbox" canónica del prompt maestro, dedupe ya vía `dedupe_key` (índice único condicional, `m000_base_schema.py:228`) — buen candidato a sobrevivir con solo el cambio de tipo de PK |

---

## 5. Cuentas / números / templates

| Tabla | Dueño | PK | UUIDv7-compatible | Consumidores | Clasificación |
|---|---|---|---|---|---|
| `whatsapp_numeros` | `migrations/standalone/042_whatsapp_multicanal.py:26-51` | `id TEXT NOT NULL PRIMARY KEY` | Sí | `WhatsAppConfigRepository`, `WhatsAppCredentialService`, `messaging/sender.py._get_whatsapp_config` (fallback #2), `core/services/whatsapp_service.py:WhatsAppConfig` | REUSE — candidato directo a la tabla "números/cuentas" canónica |
| `configuraciones` (prefijo `wa_`) | `migrations/m000_base_schema.py` (tabla genérica de config, no específica de WA) | `clave TEXT PRIMARY KEY` (no confirmado tipo exacto en esta fase) | Requiere verificación | `config/settings.py._read_erp_config`, `WhatsAppConfigRepository.get_config/set_config` | MERGE — es config genérica del ERP reutilizada como "secret store pobre" para WA (ver security audit); en el diseño nuevo, las claves `wa_*` deberían migrar a un `SecretStore`/tabla de cuentas dedicada, no seguir viviendo en la tabla de configuración genérica |
| `marketing_messages` | `migrations/standalone/036_whatsapp_rasa.py:50-62` | `id TEXT NOT NULL PRIMARY KEY` | Sí | `core/services/whatsapp_service.py:_render` (templates del pipeline legacy), `services/bot_pedidos.py` (no confirmado) | Candidato a **MERGE** con `whatsapp_service/messaging/templates.py` (que no está en BD, es Python — no revisado en detalle si son templates pre-aprobados de Meta o mensajes libres; **requiere verificación** si son el mismo concepto) |

---

## 6. Pedidos por WhatsApp — el pipeline paralelo (ver también inventario legacy §0)

| Tabla | Dueño | PK | UUIDv7-compatible | Consumidores | Clasificación |
|---|---|---|---|---|---|
| `pedidos_whatsapp` | `migrations/m000_base_schema.py:1093-1117` | `id TEXT NOT NULL PRIMARY KEY` | Sí | `core/use_cases/pedido_wa.py` (escritura), `core/services/pedidos_whatsapp_service.py` (lectura/ajuste), `core/app_container.py` (escalación/polling), `WhatsAppHistoryRepository`/`WhatsAppMetricsRepository` (lectura de fallback), `webapp/api_pedidos.py` (no confirmado en detalle) | **BLOCKED** — misma causa que el inventario legacy: no se puede clasificar REPLACE/DROP sin decidir primero si este pipeline sigue vivo o se reemplaza por `ventas`/`detalles_venta` |
| `pedidos_whatsapp_items` | `migrations/m000_base_schema.py:1118-1130` | `id TEXT NOT NULL PRIMARY KEY` | Sí | ídem | BLOCKED, ídem |

Nótese que, a diferencia de casi todas las demás tablas legacy, **estas dos ya tienen PK `TEXT`
(UUIDv7-compatible)** — el problema aquí no es de tipo de dato sino de **duplicidad conceptual**
frente a `ventas`/`detalles_venta` (que es lo que usa el pipeline nuevo). Cualquier plan de
consolidación de esquema debe decidir explícitamente si `pedidos_whatsapp*` se retira (y su
funcionalidad de mostrador/pesaje se reimplementa sobre `ventas`) o si se documenta como el modelo
oficial de "pedido en preparación previo a convertirse en venta" y se conecta al pipeline nuevo — hoy
ninguna de las dos cosas es cierta: son dos silos de datos independientes.

---

## 7. Handoff humano

No se encontró ninguna tabla dedicada a handoff humano (persistencia de "esta conversación está
siendo atendida por un humano, desde cuándo, por quién"). `whatsapp_service/middleware/handoff.py`
(`HandoffService`, 39 líneas) no fue leído en detalle en esta fase — **requiere verificación** si
persiste estado en alguna tabla existente (por ejemplo un campo dentro de `conversations.data_json`)
o si es puramente en memoria. Dado que el prompt maestro pide handoff humano como requisito explícito
del bounded context, esta es un área que necesita inventario propio en la fase de diseño, no cubierta
con suficiente evidencia aquí.

---

## 8. Resumen — tabla de clasificación final

| Tabla | PK actual | UUIDv7 OK | Clasificación objetivo |
|---|---|---|---|
| `conversations` | `phone TEXT` | Sí (clave natural) | REUSE |
| `message_log` | `INTEGER AUTOINCREMENT` | **No** | ALTER |
| `wa_business_idempotency` | `INTEGER AUTOINCREMENT` (clave funcional `action_key` ya única) | **No** (PK) | ALTER |
| `notification_inbox` | `INTEGER AUTOINCREMENT` | **No** | ALTER |
| `wa_event_log` | `TEXT` (según migración 050 — pero el código asume `INTEGER` en 2 de 3 sitios) | Sí en el esquema real, **pero el código está roto contra él** | ALTER el código (bug), no la tabla — prioridad máxima |
| `whatsapp_queue` | `TEXT` | Sí | MERGE hacia outbox único (hoy solo lo usa el pipeline legacy) |
| `wa_reminder_queue` | `TEXT` | Sí | REUSE |
| `whatsapp_numeros` | `TEXT` | Sí | REUSE |
| `wa_message_queue` | — tabla no existe — | N/A | DROP la referencia en código (2 repositorios) |
| `bot_sessions` | `numero TEXT` (clave natural) | Sí | BLOCKED (depende de Rasa) |
| `rasa_sessions` | `TEXT` | Sí | BLOCKED (depende de Rasa) |
| `marketing_messages` | `TEXT` | Sí | MERGE con templates del microservicio nuevo |
| `pedidos_whatsapp` / `pedidos_whatsapp_items` | `TEXT` | Sí | BLOCKED (pipeline paralelo, decisión de producto) |
| `links_pago` | `pedido_id TEXT` | Sí | Requiere verificación de uso real |
| Tabla de handoff humano | — no existe — | N/A | Diseñar desde cero en la fase de arquitectura |

**Balance general sobre UUIDv7**: contrario a lo que se podría esperar, la mayoría de las tablas
*creadas por migración* ya usan PK `TEXT` (UUIDv7-compatible) — el esquema base del proyecto nació
razonablemente alineado con la regla. Las excepciones son, sistemáticamente, las tablas que **el
código de aplicación crea con `CREATE TABLE IF NOT EXISTS` en vez de una migración formal**
(`message_log`, `wa_business_idempotency`, `notification_inbox`, y la definición divergente de
`wa_event_log` en `erp/events.py`/`pos_notifier.py`) — es decir, la brecha de UUIDv7 correlaciona
directamente con la brecha de "toda tabla debe nacer de una migración versionada", no son dos
problemas independientes.
