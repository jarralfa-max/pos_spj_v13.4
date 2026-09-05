# WA-6 — Webhook (canal WhatsApp)

Ejecutado: 2026-09-01. §20-21 del prompt maestro: "El webhook debe validar,
persistir mensaje, crear inbox job, responder 200. Luego un worker procesa
intención." Construye esa mitad "validar+persistir+crear job" y el
mecanismo de worker — **en paralelo al webhook en vivo**
(`webhook/whatsapp.py`, que sigue siendo la ruta real en producción hoy,
sin tocar).

## Qué se construyó

- `domain/whatsapp/entities/inbox_job.py::InboundMessageJob` — máquina de
  transiciones explícita (PENDING→PROCESSING→COMPLETED/FAILED→RETRY/DEAD_LETTER),
  mismo patrón que `WhatsAppMessageDelivery` (WA-2). `InboxStatus` nuevo en
  `enums.py`.
- `infrastructure/persistence/sqlite_inbox_repository.py` — implementa
  `WhatsAppInboxRepository` (nuevo puerto). `claim_pending()` no es atómico
  frente a workers concurrentes — documentado como límite de un solo
  proceso, mismo criterio que el cache de nonces de `service_auth.py` (WA-1).
- `infrastructure/webhooks/webhook_processor.py::WebhookProcessor` —
  resuelve el número de canal por `phone_number_id`, deduplica por
  `provider_message_id` (usa el `UNIQUE` de `whatsapp_messages`, WA-3),
  resuelve/crea `WhatsAppIdentity`, reutiliza o abre `WhatsAppConversation`,
  persiste el `WhatsAppMessage` y crea su `InboundMessageJob`. Reutiliza el
  parseo real (`models/message.py::IncomingMessage.from_webhook`), no lo
  reinventa.
- **Hallazgo real, no un detalle menor**: `whatsapp_conversations.channel_number_id`
  es `NOT NULL` (WA-3) — un mensaje de un número no registrado en
  `whatsapp_channel_numbers` no puede procesarse. Nuevo
  `ChannelNumberNotRegisteredError` en vez de fallar en silencio o inventar
  un número por defecto. El alta de números (UI/admin) sigue sin
  construirse — fuera de alcance de WA-6.
- `infrastructure/webhooks/inbox_worker.py::InboxWorker` — reclama jobs
  pendientes/retry y los procesa con un `handler` inyectable. El handler
  por defecto es un no-op explícito: WA-7 (Conversation Engine) y WA-8
  (Intent Resolution), que no existen todavía en esta pasada, son quienes
  proveerán el handler real. 5 intentos antes de dead letter (mismo orden
  de magnitud que el backoff legacy de `whatsapp_queue`). No es un
  scheduler — `run_once()` es invocable, correr en loop es una decisión de
  despliegue fuera de alcance.
- CompositionRoot (WA-4): +3 servicios (`inbox` repo, `webhook_processor`,
  `inbox_worker`) — `REQUIRED_SERVICES` pasó de 9 a 12.
- Health check `inbox_worker` (antes placeholder `UNKNOWN` fijo desde
  WA-4) ahora consulta profundidad/antigüedad real de `whatsapp_inbox` —
  con la salvedad honesta documentada de que esto NO confirma que un
  worker esté corriendo activamente, solo que la cola es consultable y no
  acumula backlog anormal. Umbrales (50/500 pendientes, 5min/1h de
  antigüedad) marcados como no calibrados contra tráfico real todavía.

## No tocado

`webhook/whatsapp.py` (el webhook en vivo) sigue procesando síncronamente
vía `MessageRouter`/flows/. `get_message_status` (WA-5) sigue sin
consumidor real de sus resultados de webhook `statuses` — ese cableado
específico (leer `statuses[]` del payload y actualizar
`WhatsAppMessageDelivery`) no se construyó en esta fase; quedó fuera para
mantener el alcance en "el mensaje entra y se encola", no "todo lo que un
webhook completo podría hacer".

## Tests

69 tests nuevos, todos en verde: `test_inbox_job_entity.py` (12),
`test_sqlite_inbox_repository.py` (7), `test_webhook_processor.py` (8 —
feliz camino, dedupe, número no registrado), `test_inbox_worker.py` (7 —
éxito, fallo con retry, fallo hasta dead letter, límite), más accessors de
CompositionRoot y el nuevo health check. Suite completa: **347 passed, 11
failed** (mismos preexistentes). Smoke test real (`TestClient` contra
`main.py`, DB bootstrapeada): sigue arrancando y `/health` responde 200.

## Siguiente fase

WA-7 — Conversation Engine (state machine real sobre lo que WA-2 ya
modeló, timeout, reset) — el primer candidato real para ser el `handler`
del `InboxWorker`.
