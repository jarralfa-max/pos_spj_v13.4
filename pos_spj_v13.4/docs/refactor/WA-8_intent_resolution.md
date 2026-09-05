# WA-8 — Intent Resolution (canal WhatsApp)

Ejecutado: 2026-09-01. §27-29 del prompt maestro: catálogo de intenciones +
resolución por capas, deteniéndose en la primera que resuelve, sin que el
clasificador/LLM ejecute nunca una operación de negocio.

## Qué se construyó

- `domain/whatsapp/value_objects/intent_resolution.py` — `IntentEntity`
  (§30: value/normalized_value/confidence/source/validation_status,
  `UNVALIDATED` por defecto — nada de una IA se confía sin validación de
  dominio posterior) e `IntentResolution` (intent/confidence/source/entities).
- `domain/whatsapp/provider_ports.py::IntentAIProvider` — puerto §29,
  `classify(text, context) -> Optional[IntentResolution]`. Retornar `None`
  es "no se pudo clasificar", nunca se inventa una intención de bajo
  alcance.
- `application/intent_resolution_service.py::IntentResolutionService` —
  las 6 capas de §28, en orden, deteniéndose en la primera que resuelve:
  1. **Interactive** — mapa determinista de los IDs de botón/lista reales
     que ya usa `messaging/interactive.py` en producción (`menu_pedido`,
     `menu_cotizacion`, `pago_link`, etc.) — no inventados.
  2. **Expected state** — `conversation.context.expected_intent` (WA-2,
     §31) si está seteado.
  3. **Reglas** — coincidencia de palabras clave sobre texto en minúsculas
     (saludo/ayuda/menú/cancelar/opt-out/handoff/estado de pedido...) —
     deliberadamente acotado, no intenta ser el clasificador.
  4-5. **Clasificador/LLM** — mismo puerto `IntentAIProvider`; por defecto
     `NullIntentAIProvider` (siempre `None` — ver más abajo).
  6. **Human handoff** — si nada resolvió, `Intent.HUMAN_HANDOFF` con
     `source=UNRESOLVED`, nunca una intención adivinada.
- `intent_to_conversation_signal()` — puente hacia `ConversationEngine`
  (WA-7): solo `HUMAN_HANDOFF`/`OPT_OUT` producen
  `ConversationSignal.HANDOFF_REQUESTED`; toda intención de negocio
  (`CREATE_ORDER`, `PAY_ORDER`...) produce `MESSAGE_RECEIVED` — deliberado,
  porque ningún caso de uso real todavía ejecuta esas intenciones (WA-9+).
- CompositionRoot: +1 servicio (`intent_resolution_service`) —
  `REQUIRED_SERVICES` pasó de 13 a 14.

## Honesto sobre el hueco real — sin clasificador/LLM conectado

`NullIntentAIProvider` siempre retorna `None`, forzando el fallback a
human handoff en la capa 6 para cualquier texto libre que no matchee una
regla. **Existe una versión legacy real** (`ai/intent_resolver.py` +
`parser/intent_parser.py`, con clasificador local + cliente de IA + log de
auditoría) pero no se conectó aquí — depende de `ProductMatcher`
(catálogo de productos vía SQLite directo) y `OllamaClient`, que son
infraestructura de catálogo/ERP más propia del alcance de WA-9 que de esta
fase. Conectarla ahora habría significado o bien mezclar responsabilidades
de catálogo dentro de "resolución de intención", o bien construir un
adaptador apurado sin las garantías que WA-9 debe establecer primero. El
punto de extensión (`IntentAIProvider`) ya existe y está probado con un
proveedor falso — conectar la implementación real es un cambio de una
línea en el `CompositionRoot` cuando corresponda, no un rediseño.

## Integración con InboxWorker — también diferida, con razón documentada

`IntentResolutionService` **no** se conectó como `handler` de
`InboxWorker` (WA-6) en esta fase. Razón real, no una excusa: la entidad
de dominio `WhatsAppMessage` (WA-2) no persiste el texto/interactive_id
crudo del mensaje — solo metadata (`payload_reference` existe como campo
pero nada lo llena todavía). Esto es intencional en el diseño original
(§16: `MessageRetentionPolicy`, que no se ha construido en ninguna fase de
este pipeline) pero significa que, tal como está hoy, un mensaje procesado
de forma asíncrona (worker, en otro momento/proceso) no tiene acceso al
contenido que `IncomingMessage` sí tenía en el momento del webhook. Cerrar
esto requiere decidir la política de retención primero, no improvisar
guardar el texto crudo sin esa política — se deja documentado como el
hueco real que es, no resuelto con un parche.

## Tests

41 tests nuevos, todos en verde: `test_intent_resolution_service.py` (28
— cada capa por separado, orden de precedencia entre capas, proveedor de
IA falso invocado/no invocado según corresponda), `test_intent_resolution_value_objects.py`
(6), accessors de `CompositionRoot` (+2). Suite completa: **422 passed, 11
failed** (mismos preexistentes). Smoke test real (`TestClient` contra
`main.py`): sigue arrancando, `/health` 200.

## Siguiente fase

Con esto se cierran las fases WA-6/7/8 (Webhook → Conversation Engine →
Intent Resolution) — el "cerebro" conversacional del canal existe y está
probado, aunque todavía no conectado al webhook en vivo ni a un
clasificador real. WA-9 (ERP Contracts) es la siguiente fase pedida, y es
la primera que requiere una decisión de producto que sigue pendiente desde
WA-0: cuál de las tres pipelines paralelas de pedidos por WhatsApp
(microservicio oficial vs. stack legacy vs. Rasa) es la autoritativa —
sin esa respuesta, diseñar contratos de "Orders" concretos arriesga
construir el contrato equivocado.
