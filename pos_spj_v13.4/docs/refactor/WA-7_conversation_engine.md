# WA-7 — Conversation Engine (canal WhatsApp)

Ejecutado: 2026-09-01. §26-27 del prompt maestro: máquina de estados real
sobre lo que WA-2 ya modeló (`WhatsAppConversation`), separando "qué señal
mueve a qué estado" (nuevo, dominio) de "cómo se aplica y valida" (ya
existía, la propia entidad).

## Qué se construyó

- `domain/whatsapp/enums.py::Intent` — catálogo de 24 intenciones (§27),
  vocabulario compartido con WA-8 (que las resuelve; esta fase solo las
  referencia como tipo).
- `domain/whatsapp/enums.py::ConversationSignal` — vocabulario distinto de
  `Intent`: "qué pasó a nivel de conversación" (bot respondió, se requiere
  aprobación, agente se unió...), no "qué quiere el cliente". Varias
  intenciones de negocio distintas pueden producir la misma señal.
- `domain/whatsapp/services/conversation_state_machine.py::next_state()` —
  tabla de transición pura (estado, señal) → estado. Dos señales
  universales (`BLOCK`→BLOCKED, `TIMEOUT`→EXPIRED) aplican desde cualquier
  estado, incluso uno terminal (auditar un bloqueo tardío no debe
  ignorarse). Un par (estado, señal) sin regla definida lanza
  `UnhandledConversationSignalError` — mejor fallar explícito que adivinar
  una transición.
- `application/conversation_engine.py::ConversationEngine` — aplica
  `next_state()` sobre una `WhatsAppConversation` real y persiste solo si
  el estado cambió; `check_timeout()` (reutiliza
  `config.settings.CONVERSATION_TIMEOUT_MINUTES`, no reintroduce un
  default nuevo — usa `last_message_at` si existe, si no `opened_at`);
  `reset()` (limpia el flujo activo vía `clear_active_flow()` de WA-2 y
  regresa a OPEN).
- **Reset respeta el invariante de WA-2, no lo esquiva**: una conversación
  terminal (RESOLVED/CLOSED/EXPIRED/BLOCKED) no puede "reabrirse in-place"
  — ese invariante ya lo protege `WhatsAppConversation.transition_to()`
  desde WA-2, a propósito. `reset()` sobre una conversación terminal lanza
  `CannotResetTerminalConversationError` en vez de forzar el estado; la
  operación correcta para retomar contacto con un cliente cuya última
  conversación ya cerró es abrir una nueva
  (`WhatsAppConversationRepository.get_open_for_identity` ya devuelve
  `None` en ese caso, y `WebhookProcessor`, WA-6, ya abre una conversación
  nueva cuando eso pasa).
- CompositionRoot: +1 servicio (`conversation_engine`) — `REQUIRED_SERVICES`
  pasó de 12 a 13.

## No tocado / diferido a propósito

`ConversationEngine` **no** se conectó como `handler` de `InboxWorker`
(WA-6) todavía — hacerlo requeriría una señal real derivada de la
intención del mensaje entrante, y eso es exactamente lo que WA-8 (Intent
Resolution) construye a continuación. Conectar el motor con una señal
inventada solo para demostrar la integración habría sido peor que
dejarlo pendiente con la razón documentada.

## Tests

49 tests nuevos, todos en verde: `test_conversation_state_machine.py`
(31 — flujo normal, handoff desde cualquier estado activo, señales
universales incluso sobre estado terminal, señal sin regla definida
lanza error) y `test_conversation_engine.py` (18 — persiste solo en
cambio real, timeout con `last_message_at` vs `opened_at`, timeout
respeta default de config, reset limpia flujo sin tocar
customer/branch, reset rechaza conversación terminal). Suite completa:
**396 passed, 11 failed** (mismos preexistentes). Smoke test real
(`TestClient` contra `main.py`): sigue arrancando, `/health` 200.

## Siguiente fase

WA-8 — Intent Resolution: resolución por capas (interactive determinista →
estado esperado → reglas → clasificador → LLM fallback → handoff). Primer
consumidor real que podrá alimentar `ConversationEngine` con una señal
derivada de una intención real, y candidato final para el `handler` de
`InboxWorker`.
