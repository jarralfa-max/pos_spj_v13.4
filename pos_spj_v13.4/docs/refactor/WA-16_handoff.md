# WA-16 — Handoff (canal WhatsApp)

Ejecutado: 2026-09-02. §32 del prompt maestro.

## Qué se construyó

- `domain/whatsapp/entities/handoff_request.py::HandoffRequest` —
  registro persistente de la solicitud de escalación (motivo, a quién se
  asignó, cuándo se resolvió). Distinto de
  `ConversationState.HANDOFF_REQUESTED`/`HUMAN_ACTIVE` (WA-2/WA-7, el
  estado de la conversación en sí) — mismo criterio de "rastro propio,
  no el objeto que orquesta" que `OrderDraft`/`DeliveryRequest`.
- Migración **247** (`whatsapp_handoff_requests`).
- `domain/whatsapp/erp_ports.py::StaffDirectoryApiClient` +
  `infrastructure/erp_clients/erp_bridge_clients.py::ErpBridgeStaffDirectoryApiClient`
  — envuelve `ERPBridge.get_staff_phones` (ya real, el mismo método que
  usa hoy `middleware/handoff.py`). Se registra en el MISMO branch de
  `_build_erp_clients()` (WA-9) que los otros 6 clientes — comparte el
  mismo `ERPBridge`/degradación a `UnavailableErpClient`.
- `application/handoff_service.py::HandoffCoordinator.request_handoff()`
  — el reemplazo, dentro de la arquitectura nueva, de
  `middleware/handoff.py::HandoffService.escalar()` (legacy, sigue vivo,
  sin tocar). Notifica gerente → cualquier staff de sucursal (mismo
  fallback que el legacy) → avisa al cliente, y ADEMÁS lo que el legacy
  no hacía: transiciona `ConversationState` vía `ConversationEngine`
  (WA-7, señal `HANDOFF_REQUESTED`, ya definida desde WA-7/WA-8) y deja
  un registro persistente.

## Idempotencia simple (no por fingerprint)

Si ya existe una `HandoffRequest` OPEN/ASSIGNED para la conversación, una
segunda solicitud NO vuelve a notificar al staff — evita spamear al mismo
gerente si el cliente insiste "hablar con alguien" varias veces mientras
espera. Verificado con un test dedicado
(`test_second_request_for_same_conversation_does_not_notify_again`).

## Envío síncrono, no vía outbox — honesto, no un descuido

WA-17 (Outbox worker) todavía no existe en este punto del árbol. Igual
que el legacy `HandoffService` y que TODO el canal hasta ahora (WA-1..15
—nada usa `whatsapp_outbox` todavía, ver hallazgo original de WA-0/WA-3),
esto envía directo vía `ProviderGateway` (WA-5). Se documenta como
candidato natural a migrar cuando WA-17 exista, no se fuerza esa
dependencia hacia adelante desde aquí.

## Honestamente fuera de alcance

`HandoffCoordinator.resolve()` marca la `HandoffRequest` como resuelta
pero NO transiciona `ConversationState` de vuelta (de `HUMAN_ACTIVE` a
`RESOLVED`, por ejemplo) — son dos ciclos de vida relacionados pero
distintos: un agente humano puede seguir conversando después de que su
ticket de "atención requerida" se cierra. Conectar ambos ciclos es
trabajo de orquestación (qué evento real dispara "el agente terminó"),
no de esta fase.

CompositionRoot: +3 servicios (`staff_directory`, `handoff_requests`,
`handoff_coordinator`) — `REQUIRED_SERVICES` pasó de 33 a 36.

## Tests

56 tests nuevos: `test_handoff_request_entity.py` (7),
`test_sqlite_handoff_request_repository.py` (5), `test_handoff_service.py`
(7 — incluida la no-doble-notificación y el fallback gerente→staff),
accessors de `CompositionRoot` (+3, incluida la variante con esquema
real), bump de conteo de tablas (17→18) + test de migración 247.

Suite completa: **612 passed, 11 failed** (mismos preexistentes desde
WA-1).

## Siguiente fase

WA-17 (Outbound Messaging / Outbox worker) — cierra el gap que WA-0/WA-3
documentaron ("el microservicio envía síncrono, sin outbox persistido") y
se convierte en el primer camino de envío real para WA-18 (Notificaciones).
