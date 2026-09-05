# WA-17 — Outbound Messaging / Outbox worker (canal WhatsApp)

Ejecutado: 2026-09-02. §21-22 del prompt maestro.

## Hallazgo que fija el alcance

WA-0 y WA-3 documentaron el mismo gap desde el principio: *"el
microservicio oficial envía mensajes SÍNCRONAMENTE, con cero outbox
persistido"* — la tabla `whatsapp_outbox` existía desde la migración 243
(WA-3) pero sin repositorio ni despachador propio. WA-1 a WA-16 enteros
siguieron enviando (cuando enviaban algo) directo vía `ProviderGateway`
(WA-5) — WA-16 (Handoff) lo hizo explícito en su propio doc. WA-17 cierra
ese gap.

## Qué se construyó

- `domain/whatsapp/entities/outbox_message.py::OutboxMessage` — refleja
  1:1 el esquema real de `whatsapp_outbox` (WA-3). `message_id`/
  `conversation_id`/`channel_number_id` opcionales (igual que la tabla,
  sin `NOT NULL`) — no se fuerza que cada envío en cola tenga primero un
  `WhatsAppMessage` (WA-2) creado; eso sería una segunda pieza de trabajo
  (modelar el ciclo de vida completo mensaje saliente → delivery) fuera
  del alcance concreto de "colar y despachar". Backoff simple por tabla
  fija (`BACKOFF_SECONDS`), tope en `MAX_ATTEMPTS=5` antes de
  `DEAD_LETTER` — mismo orden de magnitud que `InboxWorker` (WA-6).
- `infrastructure/persistence/sqlite_outbox_repository.py` — mismo
  patrón de "claim no atómico entre procesos, aceptable en un solo
  proceso" ya documentado y aceptado en `sqlite_inbox_repository.py`
  (WA-6). `claim_due()` filtra por `status='PENDING' AND (next_retry_at
  IS NULL OR next_retry_at <= now)`.
- `application/outbound_message_service.py::OutboundMessageService` — el
  único punto para encolar (`enqueue_text`/`enqueue_template`).
  Idempotente sobre `operation_id` cuando el llamador lo provee
  (`whatsapp_outbox.operation_id` es `UNIQUE` desde WA-3) — el consumidor
  natural de esto es WA-18 (Notificaciones): reintentar la misma
  notificación de negocio no duplica el mensaje en la cola.
- `infrastructure/webhooks/outbound_dispatcher.py::OutboundDispatcher.run_once()`
  — espejo exacto del patrón "claim → intentar → completar/reintentar/
  dead-letter" de `InboxWorker` (WA-6), en sentido saliente. Despacha vía
  `ProviderGateway.send_text`/`send_template` (WA-5) — ningún envío
  nuevo, reutiliza el gateway ya construido.

CompositionRoot: +3 servicios (`outbox`, `outbound_message_service`,
`outbound_dispatcher`) — `REQUIRED_SERVICES` pasó de 36 a 39. Se
actualizó la tabla de "pendientes" en el docstring del módulo:
`OutboxRepository`/`OutboundMessageDispatcher` (antes "pendiente WA-17")
y `HandoffCoordinator`/`AgentRepository` (antes "pendiente WA-16") ya no
figuran como pendientes — `AgentRepository` se deja como "futuro"
propiamente dicho (`HandoffCoordinator` asigna por teléfono de staff, sin
directorio de agentes/turnos).

## Nada del canal usa esto todavía — honesto, no un descuido

Igual que cada mecanismo nuevo desde WA-4 (`ApplicationFactory`,
`InboxWorker`, `ConversationEngine`...), `OutboundDispatcher`/
`OutboundMessageService` existen probados y wireados en el
`CompositionRoot`, pero NINGÚN servicio existente (WA-10..16) fue
retrofitteado para usarlos — `HandoffCoordinator` (WA-16) sigue enviando
directo vía `ProviderGateway`, como su propio doc ya adelantaba. El
primer consumidor real será WA-18 (Notificaciones), la fase inmediata
siguiente — retrofittear servicios ya cerrados y probados no es parte de
esta fase.

## Tests

75 tests nuevos: `test_outbox_message_entity.py` (13 — incluido el
backoff y el paso a `DEAD_LETTER` tras `MAX_ATTEMPTS`),
`test_sqlite_outbox_repository.py` (9 — incluida la ventana de reintento),
`test_outbound_message_service.py` (7 — incluida la deduplicación real
por `operation_id`), `test_outbound_dispatcher.py` (7 — incluido el
reintento agendado y el payload desconocido), accessors de
`CompositionRoot` (+3).

Suite completa: **650 passed, 11 failed** (mismos preexistentes desde
WA-1).

## Siguiente fase

WA-18 (Notificaciones) — primer consumidor real de
`OutboundMessageService`: reemplaza (en paralelo, sin tocar
`router/notify_router.py`) el envío síncrono de `/api/notify/*` por uno
que encola vía outbox.
