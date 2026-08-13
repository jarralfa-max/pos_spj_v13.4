# CRM-9 — Privacidad: Consentimientos, Preferencias, Solicitudes, Retención

Fecha: 2026-08-12. Depende de CRM-0 (auditoría), CRM-1 (guardrails —
`customer_privacy` ya existía como paquete vacío con la docstring
"CustomerConsent, CustomerCommunicationPreference, CustomerPrivacyRequest.
See master prompt §41-44"), CRM-2 (seguridad — `CustomerPermissions.
CONSENT_*`/`PRIVACY_REQUEST_*`/`SENSITIVE_DATA_*` ya existían sin
consumidor, así como `CustomerSegregationOfDutiesPolicy.
enforce_anonymization_preserves_audit()` y
`CustomerAuthorizationPolicy.authorize_exception()`/
`CustomerAuthorizationGrant`, esta última ya consumida una vez en CRM-8),
CRM-3 (Customer Master — `Customer.mark_anonymized()` fue construida ahí
explícitamente para que esta fase la llamara), CRM-8 (precedente directo:
mismo patrón de sub-bounded-context sibling que reutiliza el stack de
autorización de `customers`).
Fuente de diseño: `docs/refactor/customers_crm_master_prompt.md` §41-44.

Con esta fase se completan los cinco sub-bounded-contexts que CRM-1
scaffoldeó vacíos (`customers`, `crm`, `customer_service`, `customer_credit`,
`customer_privacy`) — todos tienen ahora código real.

## Decisiones de alcance (documentadas, no adivinadas)

- **`CustomerConsent` es un log append-only, no una fila que se
  sobreescribe.** Capturar consentimiento de nuevo para el mismo
  (cliente, tipo) crea una fila nueva que sucede a la anterior — la
  evidencia histórica completa queda auditable (§75 protege
  explícitamente "evidencia de consentimiento" como dato sensible).
  `CustomerCommunicationPreference` es la única excepción: es un registro
  1:1 por cliente (como `CustomerCreditProfile` en CRM-8), no un log.
- **`EXPIRED` nunca se persiste.** Mismo patrón que CRM-6/7/8 (`OVERDUE`,
  `SLABreachStatus`, indirectamente el gap de identidad de CxC): nada
  "transiciona" un consentimiento a EXPIRED, simplemente se vuelve cierto
  cuando pasa `expires_at` mientras sigue en GRANTED. La columna `status`
  solo guarda PENDING/GRANTED/WITHDRAWN/NOT_REQUIRED;
  `CustomerConsent.effective_status()` deriva EXPIRED dinámicamente.
- **No hay estado `REJECTED`/`DECLINED` para consentimiento.** El enum de
  estados de §41-44 no lo incluye — capturar/confirmar consentimiento es
  la vía primaria; una solicitud de opt-in que nunca se confirma
  simplemente permanece PENDING (no hay "declinar" explícito en la lista
  literal del master prompt).
- **`AnonymizeCustomerUseCase` es un caso de uso separado de
  `CompletePrivacyRequestUseCase`**, no una rama condicional dentro de él.
  `CompletePrivacyRequestUseCase` rechaza explícitamente completar una
  solicitud `ANONYMIZATION`/`CANCELLATION` (`requires_anonymization_
  workflow()`), así nadie puede saltarse el segundo autorizador llamando
  a la vía genérica por error.
- **Alcance real de la anonimización — solo campos de nombre propios de
  `Customer`.** §44: "Anonimización respeta obligaciones fiscales, ventas
  históricas, CxC, auditoría, prevención de fraude, retención legal." Se
  redactan `display_name`/`first_name`/`last_name`/`second_last_name`/
  `commercial_name`. **`legal_name` NO se toca** (atado a obligaciones
  fiscales/RFC). `CustomerContactPerson`/`CustomerAddress`/
  `CustomerTaxProfile` y cualquier dato en Ventas/Finanzas **tampoco se
  tocan** — igual que CRM-8 nunca creó un ledger de CxC paralelo, esta
  fase no reescribe datos que pertenecen a otros bounded contexts. Un
  alcance más completo de redacción (contactos/direcciones tras vencer la
  retención legal) queda como trabajo futuro explícito, no implementado.
- **`CustomerDataRetentionPolicy` no modela el eje "por empresa"** — este
  código no tiene un concepto de multi-tenant en ningún otro lugar del
  módulo; las políticas aplican a nivel de toda la instalación. Los otros
  tres ejes (`customer_type`, `data_category` como valor libre en
  mayúsculas, `customer_status`) sí se modelan con comodín-o-valor,
  igual que `ServiceLevelPolicy` (CRM-7).
- **`CustomerCommunicationPreference` no tiene permiso propio en el
  catálogo original de CRM-2** — retroactivo: se agregaron
  `COMMUNICATION_PREFERENCE_VIEW`/`COMMUNICATION_PREFERENCE_MANAGE`
  (`CLIENTES.preferencia_comunicacion.*`). Reusar `CONSENT_*` habría sido
  un desajuste semántico (una preferencia de horario/idioma no es un
  otorgamiento legal de consentimiento). Mismo patrón que
  `TASKS_RESCHEDULE` (CRM-6) / `SLA_MANAGE` (CRM-7) / `CREDIT_CLOSE`
  (CRM-8). Verificado 1:1 sin drift: 75→77 permisos de
  `CustomerPermissions`.
- **`CustomerDataRetentionPolicy` SÍ usa un permiso ya existente**
  (`SETTINGS_VIEW`/`SETTINGS_MANAGE`, genéricos de configuración de
  módulo) — a diferencia de las adiciones retroactivas anteriores, aquí
  el permiso correcto ya estaba en el catálogo desde CRM-2 sin
  consumidor, así que no hizo falta agregar nada nuevo.

## Dominio (`backend/domain/customer_privacy/`)

- **`enums.py`** — `ConsentType` (8 valores), `ConsentStatus`,
  `ConsentChannel` (dónde se capturó la evidencia — distinto del canal de
  preferencia de comunicación), `PreferredChannel`, `PrivacyRequestType`
  (7 valores), `PrivacyRequestStatus` (6 valores).
- **`entities/customer_consent.py`** — `CustomerConsent`. `capture()`
  otorga directamente (vía sincrónica, la más común); `request()`→
  `confirm()` para flujos de doble opt-in asíncronos; `mark_not_required()`
  para tipos que no aplican a un cliente. `withdraw(reason)` requiere
  motivo.
- **`entities/customer_communication_preference.py`** —
  `CustomerCommunicationPreference`. Registro de configuración simple, sin
  máquina de estados.
- **`entities/customer_privacy_request.py`** — `CustomerPrivacyRequest`,
  agregado raíz con folio (`PrivacyRequestCode`, "PRIV-NNNNNN" — mismo
  patrón que Lead/Opportunity/ServiceCase). Ciclo:
  RECEIVED→VALIDATING→IN_PROGRESS→{COMPLETED,REJECTED,CANCELLED}.
  `related_consent_id` opcional enlaza una solicitud `CONSENT_WITHDRAWAL`
  al consentimiento específico que debe retirarse al completarse.
- **`entities/customer_data_retention_policy.py`** —
  `CustomerDataRetentionPolicy` + **`policies/data_retention_policy_resolver.py`**
  (`DataRetentionPolicyResolver`), mismo patrón wildcard-o-valor y
  resolución por mayor especificidad que `ServiceLevelPolicyResolver`
  (CRM-7).
- **`events.py`** — `CustomerPrivacyEvents` (13 eventos) +
  `build_event_payload()` propio.
- **`repository_ports.py`** — cuatro puertos.
- **`exceptions.py`** — solo errores propios — sin duplicar los de
  autorización/SoD de `customers` (ver arriba, mismo criterio que CRM-8).

## Infraestructura

- **`backend/infrastructure/db/schema/customer_privacy_schema.py`** —
  archivo nuevo, 7 tablas: `customer_consents`,
  `customer_communication_preferences` (`UNIQUE(customer_id)`),
  `customer_data_retention_policies`, `customer_privacy_requests`,
  `customer_privacy_audit_log` (incluye `authorized_by_user_id` desde el
  diseño inicial, igual que CRM-8 — tabla nueva, sin necesidad de `ALTER
  TABLE` retroactivo), `customer_privacy_outbox`,
  `customer_privacy_processed_events`.
- **`migrations/standalone/189_customer_privacy_bounded_context_schema.py`**
  — número verificado contra `engine.py` y el directorio de migraciones
  inmediatamente antes de crear el archivo (189 libre). Registrada en
  `migrations/engine.py`. Verificado contra el bootstrap completo: 575
  tablas totales.
- **`backend/infrastructure/db/repositories/customer_privacy/`** — cuatro
  repositorios + `support_repositories.py` + `unit_of_work.py` +
  `base.py`. **Bug real detectado y corregido durante las pruebas de
  integración**: `CustomerConsentRepository.get_latest()`/
  `list_for_customer()` ordenaban solo por `created_at` (precisión de
  segundo) — dos capturas en el mismo segundo empataban y el orden
  quedaba indeterminado. Corregido a `ORDER BY created_at DESC, id DESC`
  (el id UUIDv7 es time-ordered con precisión mucho mayor, el desempate
  real y determinista).

## Aplicación (`backend/application/customer_privacy/`)

- **`use_cases/consent_use_cases.py`** — `CaptureConsentUseCase`,
  `RequestConsentUseCase`, `ConfirmConsentUseCase`, `WithdrawConsentUseCase`,
  `MarkConsentNotRequiredUseCase`.
- **`use_cases/communication_preference_use_cases.py`** —
  `SetCommunicationPreferenceUseCase` (upsert: crea el registro si no
  existe, actualiza si ya existe — un solo caso de uso para ambos casos).
- **`use_cases/privacy_request_use_cases.py`** —
  `CreatePrivacyRequestUseCase`, `ValidatePrivacyRequestUseCase`,
  `StartProcessingPrivacyRequestUseCase`, `RejectPrivacyRequestUseCase`,
  `CancelPrivacyRequestUseCase`, `CompletePrivacyRequestUseCase` (genérico
  para ACCESS/RECTIFICATION/OPPOSITION/EXPORT/CONSENT_WITHDRAWAL — esta
  última también retira el consentimiento enlazado en la misma
  transacción; rechaza ANONYMIZATION/CANCELLATION explícitamente).
- **`use_cases/anonymize_customer_use_case.py`** —
  `AnonymizeCustomerUseCase`, el único punto donde Privacidad y Customer
  Master se tocan. Segundo consumidor real de
  `CustomerAuthorizationPolicy.authorize_exception()`/
  `CustomerAuthorizationGrant` (el primero fue CRM-8) — `authorized_by`
  debe ser distinto de `requested_by` (quien registró la solicitud
  originalmente), verificado dos veces (política y en el propio value
  object). Primer consumidor real de
  `CustomerSegregationOfDutiesPolicy.enforce_anonymization_preserves_
  audit()` (sin llamador desde CRM-2). Atomicidad cross-context: mismo
  patrón de conexión compartida y commit/rollback manual que
  `ConvertLeadUseCase` (CRM-4).
- **`use_cases/retention_policy_use_cases.py`** —
  `CreateDataRetentionPolicyUseCase` (`SETTINGS_MANAGE`).
- **`queries/customer_consent_query_service.py`** —
  `CustomerConsentQueryService.is_active()`: el único método sancionado
  para que otros módulos (WhatsApp, Notification Management) verifiquen
  consentimiento antes de enviar un mensaje — "No inferir consentimiento
  por tener teléfono/correo" (§44) se cumple porque esta es la única vía,
  nunca un atajo que infiera desde otro dato.
- **`queries/customer_privacy_request_query_service.py`**,
  **`queries/customer_communication_preference_query_service.py`** — sin
  eje OWN/TEAM (permisos planos, mismo criterio que CRM-6 para
  Actividades/Tareas/Notas).

## Verificación

```bash
python -m pytest tests/unit/customer_privacy/ tests/integration/customer_privacy/ tests/architecture/test_customers_crm_*.py -q
# 98 passed, 1 skipped (routes — CRM-14)
```

- 65 tests nuevos (32 unitarios de dominio — lifecycle de `CustomerConsent`
  con derivación EXPIRED, `CustomerPrivacyRequest`, `DataRetentionPolicyResolver`
  — y 33 de integración con SQLite real: repositorios (incluido el bug de
  ordenamiento encontrado y corregido), flujo completo de solicitudes,
  retiro de consentimiento enlazado, y el flujo cruzado completo de
  anonimización con segundo autorizador obligatorio).
- Los 22 guardrails de CRM-1 se re-ejecutaron completos (primera vez con
  código real en `customer_privacy` bajo esos escaneos) y siguieron en
  verde sin ajustes.
- 572 tests de `tests/unit/customers/` + `tests/integration/customers/` +
  `tests/unit/crm/` + `tests/integration/crm/` +
  `tests/unit/customer_service/` + `tests/integration/customer_service/` +
  `tests/unit/customer_credit/` + `tests/integration/customer_credit/` +
  `tests/unit/customer_privacy/` + `tests/integration/customer_privacy/`
  pasan juntos.
- Sintaxis global limpia; bootstrap completo de migraciones verificado
  (575 tablas).

## Pendiente (próximas fases)

- **CRM-10 (Segmentación):** cuando aterrice, `CustomerDataRetentionPolicy`
  gana el eje `segment_id` si el master prompt lo requiere para ese
  bounded context específico (no aplica aquí, retención no lo pidió por
  segmento).
- **CRM-11 (Calidad/duplicados/fusión):** §45-46, explícitamente fuera del
  alcance de "consentimientos, preferencias, solicitudes, retención" que
  pidió esta fase.
- **CRM-12 (Customer 360):** consumidor natural de
  `CustomerConsentQueryService`/`CustomerPrivacyRequestQueryService` para
  la tab "Consentimientos" del expediente.
- Redacción más completa en `AnonymizeCustomerUseCase` (contactos,
  direcciones, tras vencer la retención legal aplicable) — alcance
  explícitamente diferido, no implementado.
- `SENSITIVE_DATA_VIEW`/`SENSITIVE_DATA_EXPORT`/`SENSITIVE_DATA_UNMASK` y
  `CONSENT_EVIDENCE_VIEW` no tienen consumidor propio todavía — candidatos
  para cuando exista una vista de expediente que use `FieldVisibility`
  sobre más campos que solo crédito (CRM-8 fue el primer consumidor real
  de esa maquinaria).
