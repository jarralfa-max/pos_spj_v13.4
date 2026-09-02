# WA-2 — Dominio base (canal WhatsApp)

Ejecutado: 2026-09-01. Construye el dominio puro (`whatsapp_service/domain/whatsapp/`)
para Accounts, Numbers, Identity, Conversation, Message y Events, per §6/§10-15/§55
del prompt maestro. Sin dependencias de FastAPI, SQLite ni ningún detalle de
infraestructura — es el mismo criterio que ya usa `domain/phone_number.py`.

No se wire-a nada todavía: ningún router, `main.py`, ni tabla nueva. Eso es
WA-3 (esquema limpio), WA-4 (bootstrap/composition root) y WA-9 (contratos
ERP) — este es solo el vocabulario y las invariantes del dominio.

---

## 1. Layout creado

```
whatsapp_service/domain/whatsapp/
├── __init__.py
├── _ids.py                        — UUIDv7 (REGLA CERO), mismo patrón defensivo de WA-1
├── enums.py                       — vocabularios cerrados (§10-15)
├── exceptions.py                  — solo las excepciones que WA-2 necesita
├── events.py                      — eventos de dominio puros (dataclasses, sin EventBus)
├── repository_ports.py            — Protocols de persistencia (sin implementación)
├── provider_ports.py              — Protocol del gateway de proveedor (sin implementación)
├── value_objects/
│   └── phone_number.py            — WhatsAppPhoneNumber (envuelve domain/phone_number.py)
└── entities/
    ├── business_account.py        — WhatsAppBusinessAccount, WhatsAppProviderConfiguration
    ├── channel_number.py          — WhatsAppChannelNumber
    ├── identity.py                 — WhatsAppIdentity
    ├── conversation.py             — WhatsAppConversation, ConversationSession
    ├── conversation_context.py     — ConversationContext (versionado, tipado)
    └── message.py                   — WhatsAppMessage, WhatsAppMessageDelivery
```

## 2. Accounts / Numbers (§10-11)

- `WhatsAppBusinessAccount`: `id` (UUIDv7), `provider` (META/TWILIO),
  `business_account_external_id`, `display_name`, `status`
  (DRAFT→ACTIVE/DEGRADED/SUSPENDED/DISCONNECTED/RETIRED — RETIRED es
  terminal, no se puede reactivar ni suspender), `secret_reference_id`
  (apunta al `SecretStore` de WA-1, nunca guarda el secreto mismo).
- `WhatsAppProviderConfiguration`: separada de la cuenta — versión de API y
  ajustes extra del proveedor, deliberadamente mínima (§10 no detalla más
  campos que "config del proveedor").
- `WhatsAppChannelNumber`: `account_id`, `phone_number_external_id`,
  `normalized_phone_number` (value object E.164), `branch_id`,
  `channel_role` (6 roles de §10), `status` (mismo vocabulario que la
  cuenta). **Invariante aplicado en el borde del dominio:** todo
  `channel_role` distinto de `GLOBAL_CUSTOMER_SERVICE` exige `branch_id` —
  la construcción falla si no se provee, en vez de dejar que un consumidor
  posterior "asuma sucursal Principal" (regla explícita de §11).

## 3. Identity (§12)

`WhatsAppIdentity`: `wa_id` (ID externo de Meta) + `normalized_phone`
(value object) + `customer_id` opcional + `identity_status`
(UNRESOLVED→RESOLVED→VERIFIED, o →BLOCKED/→MERGED desde cualquier estado no
terminal). El teléfono explícitamente **no** es la PK — `id` es un UUIDv7
independiente, verificado por test (`test_phone_not_used_as_id`). Vincular
a un cliente (`link_to_customer`) resuelve la identidad pero no la
reemplaza — Customers sigue siendo dueño de la identidad de negocio (§44,
fuera de alcance aquí).

## 4. Conversation (§14) + ConversationContext (§31)

- `WhatsAppConversation.open()` arranca en `OPEN`. Los 12 estados de §14
  están modelados; 4 son terminales (`RESOLVED`, `CLOSED`, `EXPIRED`,
  `BLOCKED`) — la entidad protege un invariante mínimo: **un estado
  terminal no puede transicionar a uno no-terminal** (no se reabre una
  conversación cerrada por accidente). Decidir *cuál* es el siguiente
  estado correcto según intención/timeout es responsabilidad del motor
  conversacional completo (WA-7) — esta entidad no lo intenta, solo evita
  el error más costoso.
- `ConversationContext` es una dataclass con campos explícitos y tipados
  (`customer_id`, `branch_id`, `active_order_draft_id`, `active_quote_id`,
  `delivery_address_id`, `expected_intent`, `expected_entity`,
  `last_confirmed_action` — exactamente los de §31), **no** un dict libre:
  el prompt maestro es explícito en que el contexto debe ser "versionado y
  validado" y nunca "objetos Python serializados arbitrariamente". Cada
  `with_update()` devuelve un nuevo contexto inmutable con `version + 1` y
  rechaza cualquier campo no declarado.
- `ConversationSession` modela reapertura de hilo dentro de la misma
  conversación sin perder su historial.

## 5. Message (§15)

- `WhatsAppMessage`: entidad de solo-creación (inmutable tras construirse
  — un mensaje recibido/enviado no cambia de contenido). Cubre los 13 tipos
  y 3 direcciones de §15.
- `WhatsAppMessageDelivery`: entidad de estado con **máquina de
  transiciones explícita** (`_VALID_DELIVERY_TRANSITIONS`) — a diferencia
  de `WhatsAppConversation` (que solo protege un invariante), aquí sí se
  modela la máquina completa porque §15 la especifica por completo: p. ej.
  `READ` y `DEAD_LETTER`/`CANCELLED` son terminales y no aceptan ninguna
  transición saliente; `FAILED` puede reintentarse (`RETRYING`) pero un
  reintento agotado va a `DEAD_LETTER`. `attempt_count` se incrementa en
  cada intento de envío real (`SENT`/`RETRYING`), no en cada llamada.

## 6. Events (§55, subconjunto de WA-2)

`domain/whatsapp/events.py` define objetos de dominio puros
(`ConversationOpened`, `ConversationStateChanged`, `MessageReceived`,
`MessageDeduplicated`, `MessageDeliveryStatusChanged`, `IdentityResolved`,
`IdentityBlocked`) — **no** llaman a `core.events.event_bus`; describen
solo "qué pasó". La integración con el EventBus real del ERP es WA-4
(bootstrap) / WA-18 (notificaciones). Los nombres canónicos de §55 que no
corresponden a entidades de WA-2 (`WHATSAPP_HANDOFF_*`,
`WHATSAPP_OPT_OUT_*`, `WHATSAPP_BUSINESS_OPERATION_*`) se agregan en las
fases dueñas de esas entidades (WA-16, WA-14, WA-9) — no se inventaron por
adelantado.

## 7. Puertos (repository_ports.py, provider_ports.py)

Protocols (`typing.Protocol`) sin implementación: `WhatsAppAccountRepository`,
`WhatsAppProviderConfigurationRepository`, `WhatsAppNumberRepository`,
`WhatsAppIdentityRepository`, `WhatsAppConversationRepository`,
`WhatsAppMessageRepository`, `WhatsAppProviderGateway`. Existen para que
WA-3/WA-4 (persistencia) y WA-5 (Meta Cloud API gateway) tengan un contrato
fijo contra el cual implementar, y para que ninguna capa de aplicación
futura dependa de SQLite/httpx directamente (regla 5-6 del skill de
refactor).

## 8. UUIDv7 (REGLA CERO)

Toda entidad genera su `id` vía `domain/whatsapp/_ids.py::new_id()`, que
envuelve `backend/shared/ids.py::new_uuid()` con el mismo patrón defensivo
de import ya establecido en `erp/events.py::_new_event_id()` (WA-1) —
funciona tanto vía `main.py` (que ya deja `pos_spj_v13.4/` en `sys.path`)
como en tests standalone. Ninguna entidad usa enteros, `lastrowid` ni
teléfono/wa_id como identidad — verificado por test en cada entidad
(`is_uuidv7(...)`).

## 9. Reutilización deliberada (no duplicación)

- Normalización de teléfono: `WhatsAppPhoneNumber` **envuelve**
  `domain/phone_number.py::normalize_to_e164` — no reimplementa el
  algoritmo. Sigue habiendo una sola normalización de teléfonos en todo el
  microservicio (§13).
- Enmascarado de secretos: no aplica en esta fase (WA-2 no toca secretos).

---

## Tests

Nuevos, 104 tests, todos en verde:

- `test_domain_whatsapp_accounts.py` (21)
- `test_domain_whatsapp_numbers.py` (21)
- `test_domain_whatsapp_identity.py` (19)
- `test_domain_whatsapp_conversation.py` (25)
- `test_domain_whatsapp_message.py` (16)
- `test_domain_whatsapp_events.py` (9)

Ejecutados con el mismo orden de `PYTHONPATH` que `main.py` prioriza en
producción (`whatsapp_service` → `pos_spj_v13.4` → raíz del repo — ver nota
de WA-1 sobre por qué el orden importa: `whatsapp_service/infrastructure/`
y `pos_spj_v13.4/infrastructure/` son paquetes top-level distintos con el
mismo nombre).

- Suite completa `whatsapp_service/tests/`: **190 passed, 11 failed** — los
  11 son los mismos fallos preexistentes y no relacionados ya documentados
  en `WA-1_seguridad.md` (fixtures `DummyParser` sin `.matcher` en tests de
  `intent_resolver`/`message_router`, ningún archivo de esa área tocado
  aquí tampoco).
- Sintaxis global (`ast.parse` sobre `pos_spj_v13.4/` y `whatsapp_service/`):
  sin errores.
- Sanity check de imports de los dos módulos de puertos
  (`repository_ports.py`, `provider_ports.py`): OK.

## Siguiente fase

WA-3 — Esquema limpio: migraciones nuevas (`UUIDv7`, constraints, inbox,
outbox, idempotencia, dead letter) que estas entidades necesitarán para
persistirse de verdad. Antes de eso, sigue pendiente la decisión de
producto sobre cuál de las tres pipelines de pedidos por WhatsApp es la
autoritativa (ver `whatsapp_legacy_inventory.md`, 5 ítems `BLOCKED`) — no
bloquea WA-3 en sí (el esquema del canal es independiente de esa decisión),
pero sí bloqueará WA-9/WA-10 más adelante.
