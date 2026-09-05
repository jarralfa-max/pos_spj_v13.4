# WA-14 — Clientes y consentimiento (canal WhatsApp)

Ejecutado: 2026-09-02. §44 del prompt maestro.

## Hallazgo que fija el alcance

`messaging/sender.py::_is_whatsapp_opted_out` (CRM-31) ya es un gate REAL
—consulta `customer_consents WHERE consent_type='WHATSAPP'` antes de cada
envío— pero su propio comentario lo dice explícito: *"Hoy no existe ningún
productor de estos registros en el sistema (el dominio de consentimiento
fue construido en CRM-9 pero nunca conectado a un flujo real)... en la
práctica esto siempre retorna False hasta que exista un flujo de captura
de opt-out"*. WA-14 es ese primer productor real — no se inventa un
segundo modelo de consentimiento del lado WhatsApp, se completa el lado
que faltaba del dominio ya construido en CRM-9.

## Qué se construyó

- `domain/whatsapp/consent_ports.py::ConsentApiClient` — puerto (`get_status`/
  `grant`/`opt_out`), mismo criterio de traducción-únicamente que
  `erp_ports.py` (WA-9).
- `infrastructure/erp_clients/consent_client.py::CustomerConsentApiClient`
  — envuelve `CustomerConsentRepository` (CRM-9) REAL, contra la MISMA
  conexión que el resto del `CompositionRoot` (sin conexión nueva, a
  diferencia de `ERPBridge`/WA-9 que sí necesita una). `opt_out()` es
  idempotente (no duplica fila si ya está `WITHDRAWN`) y decide
  internamente `withdraw()` (transición real desde `GRANTED`) vs. un
  nuevo `decline()` (ver abajo) cuando no hay consentimiento previo.
- **Extensión mínima y aditiva a `backend/domain/customer_privacy/entities/customer_consent.py`
  (CRM-9)**: nuevo classmethod `CustomerConsent.decline()`, que va
  directo a `WITHDRAWN` sin exigir un `GRANTED` previo. Gap real
  encontrado: el dominio CRM-9 solo modela "otorgar → retirar"
  (`withdraw()` exige partir de `GRANTED`), pero el caso real más común
  de WhatsApp es un cliente que escribe "BAJA" la PRIMERA vez que
  interactúa, sin haber otorgado nada antes — no había forma de
  persistir eso como un registro `WITHDRAWN`. Aditivo puro (no toca
  `capture`/`request`/`confirm`/`withdraw`/`mark_not_required`
  existentes); 3 tests nuevos en
  `tests/unit/customer_privacy/test_customer_privacy_entities.py`
  (80 tests de ese bounded context siguen en verde).
- `application/consent_service.py::ConsentService` — resuelve
  `customer_external_id` (el `clientes.id` legacy que ya devuelven
  `CustomersApiClient.find_by_phone`/`create_minimal`, WA-9) hacia
  `customers.id` (Customer Master, CRM-3) vía
  `ResolveLegacyCustomerUseCase` (CRM-21, reutilizado tal cual — el MISMO
  puente que ya usa `_is_whatsapp_opted_out`). Sin este puente, escribir
  con el id equivocado habría hecho que el gate real de envío nunca leyera
  lo que WA-14 escribiera — verificado con un test dedicado
  (`test_same_legacy_customer_resolves_to_the_same_bridged_id_twice`).

CompositionRoot: +2 servicios (`consent`, `consent_service`) — degrada a
`UnavailableErpClient` explícito si `customer_consents` no existe en la
conexión (mismo patrón que WA-9), verificado en ambos sentidos (degradado
y real). `REQUIRED_SERVICES` pasó de 29 a 31. Se agregó accesor público
`.connection` al root (necesario para que `ConsentService` invoque
`ResolveLegacyCustomerUseCase`, que requiere la conexión cruda).

## Honestamente fuera de alcance

No se conecta `record_opt_out`/`record_opt_in` a ningún punto de la
conversación todavía — `Intent.OPT_OUT` (WA-8) sigue mapeando a la señal
`ConversationSignal.HANDOFF_REQUESTED` sin cambios (no se tocó
`intent_resolution_service.py`). Conectar "el cliente escribió BAJA" →
`ConsentService.record_opt_out()` es un trabajo de orquestación que
depende de resolver primero el mismo gap que ya documentó WA-8
("`IntentResolutionService` no está wireada como handler de
`InboxWorker`" — nada ejecuta hoy ninguna intención resuelta, ni siquiera
`CREATE_ORDER`). WA-14 entrega la capacidad real y probada; conectarla es
alcance de una fase de orquestación futura, no de esta.

## Tests

45 tests nuevos: `test_consent_client.py` (7 — incluida la idempotencia de
`opt_out`), `test_consent_service.py` (4 — incluido el puente
legacy→Customer Master), accessors de `CompositionRoot` (+4, incluida la
variante con esquema real), 3 tests nuevos en Customer Privacy (CRM-9)
para `CustomerConsent.decline()`.

Suite del canal: **581 passed, 11 failed** (mismos preexistentes desde
WA-1). Suite de Customer Privacy (CRM-9): 80 passed, sin regresiones.

## Siguiente fase

WA-15 (Fidelidad) — lectura de puntos/nivel vía `loyalty_snapshots`
(Fidelidad), primera implementación real de `LoyaltyApiClient` (WA-9 lo
dejó como contrato sin implementación).
