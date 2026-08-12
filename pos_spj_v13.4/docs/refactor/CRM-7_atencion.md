# CRM-7 — Atención al Cliente / Casos / SLA / Escalamiento

Fecha: 2026-08-12. Depende de CRM-0 (auditoría), CRM-1 (guardrails —
`customer_service` ya existía como paquete vacío con la docstring
"CustomerServiceCase, ServiceCaseActivity, SLAInstance. See master prompt
§30-32"), CRM-2 (seguridad — `CRMPermissions.CASES_*`/`SLA_*` ya existían,
sin consumidor hasta ahora, incluyendo `CASE_VIEW_SCOPE_PERMISSIONS`),
CRM-6 (Activities/Tasks/Notes — reutilizados aquí vía
`CRMRelatedEntityType.CASE`, reservado exactamente para este momento).
Fuente de diseño: `docs/refactor/customers_crm_master_prompt.md` §30-32.
Precedente seguido: `backend/domain/crm/entities/opportunity.py` (CRM-5) +
`backend/domain/crm/entities/crm_task.py` (CRM-6) — mismo patrón entidad-
agregada + value objects + políticas + repositorios + UoW + casos de uso +
query services.

## Objetivo

Casos de atención al cliente con ciclo de vida completo, SLA configurable
(nunca hardcodeado) con seguimiento de vencimiento/riesgo, y escalamiento
con motivo/nivel/destinatario auditable.

## Decisión estructural: bounded context propio, no una extensión de `crm`

A diferencia de CRM-5/CRM-6 (que extendieron `backend/domain/crm/` y
`crm_schema.py`), esta fase vive en **`backend/domain/customer_service/`**,
**`backend/application/customer_service/`**,
**`backend/infrastructure/db/repositories/customer_service/`**, y un
archivo de esquema nuevo, **`customer_service_schema.py`** — un
sub-bounded-context completo y separado, con su propio `UnitOfWork`,
`audit_log`/`outbox`/`processed_events`. Esto no es una decisión nueva de
esta fase: CRM-1 ya había definido `customer_service` como uno de los
cinco sub-bounded-contexts del módulo (`CRM_SUBCONTEXTS = ("customers",
"crm", "customer_service", "customer_credit", "customer_privacy")` en
`tests/architecture/customers_crm_guardrails.py`), con su propio archivo de
esquema anticipado en `CRM_SCHEMA_FILES["customer_service"]`. CRM-7 es la
primera fase que llena ese paquete con código real.

**Permisos y autorización SÍ se reutilizan, no se duplican**:
`CRMAuthorizationPolicy`/`CRMPermissions`/`CRMDataScopeResolver` (de
`backend/application/crm/`) se importan directamente — CRM-2 construyó
un solo stack de autorización para toda la familia Leads/Opportunities/
Activities/Cases, y los permisos `CASES_*`/`SLA_*` ya viven ahí. Las
excepciones de permiso/alcance que se lanzan siguen siendo
`CRMPermissionDeniedError`/`CRMScopeError`/`CRMConfigurationError` — este
bounded context no define una jerarquía paralela de errores de
autorización (ver `backend/domain/customer_service/exceptions.py`).

## Decisiones de alcance (documentadas, no adivinadas)

- **`ServiceCaseActivity` no es una entidad nueva.** §30-32 la nombra junto
  a `CustomerServiceCase`/`ServiceCaseCategory`/`ServiceCaseResolution`,
  pero es exactamente `CRMActivity` (CRM-6) enlazada vía
  `related_entity_type=CRMRelatedEntityType.CASE` — el valor de enum que
  CRM-6 reservó explícitamente "para CRM-7 (Service Cases don't exist yet)
  — no use case in CRM-6 produces it, but the value exists now so CRM-7
  doesn't have to widen a CHECK constraint later." `CRMTask`/`CRMNote`
  también se reutilizan igual para tareas/notas de un caso. No se creó
  ninguna tabla paralela.
- **`escalation_level` vive solo en `SLAInstance`, no en
  `CustomerServiceCase`.** §30-32 lo lista como campo de `SLAInstance`
  únicamente; duplicarlo en el caso solo invitaría a que los dos contadores
  se desincronizaran. Si un caso no tiene SLA configurada,
  `EscalateServiceCaseUseCase` igual transiciona el caso a `ESCALATED`
  (nivel implícito 1), simplemente sin contador persistido.
- **`SLABreachStatus` sigue el mismo patrón que `CRMWorkItemStatus.OVERDUE`
  (CRM-6): PAUSED/COMPLETED se persisten (eventos explícitos: el caso entró
  en `WAITING_CUSTOMER`; se registró una resolución), pero
  ON_TIME/AT_RISK/BREACHED nunca se guardan** — dependen solo de que pase
  el tiempo, así que `SLAInstance.effective_breach_status()` los calcula
  comparando `resolution_due_at` contra "ahora", sin necesitar un job en
  segundo plano.
- **Pausar no extiende el `resolution_due_at`.** Simplificación v1
  documentada explícitamente (no silenciosa): mientras el caso está en
  `WAITING_CUSTOMER`, el estado *mostrado* se congela en PAUSED, pero la
  fecha límite original no se recalcula. Extender la fecha por la duración
  pausada es una mejora razonable a futuro, no implementada aquí — mismo
  tipo de simplificación acotada que la aproximación de "sin seguimiento"
  del forecast de CRM-5.
- **`EscalateServiceCaseUseCase` no es una política de decisión.** §30-32
  dice "Registra motivo/nivel/usuario/fecha/destinatario" — es el agente
  quien decide escalar y elige un motivo de un vocabulario cerrado
  (`EscalationReason`), no un policy que computa una decisión a partir de
  entradas (a diferencia de `LeadQualificationPolicy`). El caso de uso solo
  valida el motivo contra el enum y registra los cinco campos.
- **Segmento no se usa para resolver la política de SLA.** §30-32 pide
  "Configurable por tipo/prioridad/segmento/sucursal/canal" pero CRM-10
  (Segmentación) no existe todavía — `ServiceLevelPolicy`/
  `ServiceLevelPolicyResolver` solo emparejan por `case_type`/`priority`/
  `origin_branch_id`/`channel`; se añade `segment_id` cuando CRM-10
  aterrice, no se adivina su forma ahora.
- **`CancelServiceCaseUseCase` usa `CASES_EDIT`, no un permiso nuevo.**
  Mismo criterio que `CancelOpportunityUseCase` (CRM-5), que también usa
  `OPPORTUNITIES_EDIT` para cancelar en vez de un permiso dedicado — no
  existe (ni existía) un `CASES_CANCEL` en el catálogo de CRM-2, y
  cancelar es semánticamente una edición de estado, no un cierre con
  resolución (por eso tampoco usa `CASES_CLOSE`).

## Dominio (`backend/domain/customer_service/`)

- **`enums.py`** — `ServiceCaseType` (10 valores), `ServiceCaseStatus` (9
  estados), `ServiceCasePriority` (5 niveles), `ServiceCaseChannel`,
  `EscalationReason` (vocabulario cerrado de §30-32), `SLABreachStatus`.
- **`entities/customer_service_case.py`** — `CustomerServiceCase`, agregado
  raíz. Máquina de estados completa (NEW→ASSIGNED→IN_PROGRESS↔WAITING_*
  →ESCALATED(re-escalable)→RESOLVED→CLOSED; CANCELLED desde cualquier
  estado abierto; RESOLVED/CLOSED→reopen()→IN_PROGRESS con
  `reopen_count += 1`).
- **`entities/service_case_category.py`** — `ServiceCaseCategory`, catálogo
  configurable (mismo patrón que `CRMStageDefinition`).
- **`entities/service_case_resolution.py`** — `ServiceCaseResolution`,
  evidencia de la resolución (mismo split que `Lead`/`LeadQualification`):
  `case.resolve()` solo cambia estado, esta entidad separada guarda el
  resumen/causa raíz/satisfacción del cliente.
- **`entities/service_case_escalation.py`** — `ServiceCaseEscalation`,
  registro inmutable por evento de escalamiento (mismo patrón que
  `OpportunityStageHistory`).
- **`entities/service_level_policy.py`** — `ServiceLevelPolicy`, catálogo
  configurable de SLA con `matches()`/`specificity()` (ejes wildcard-o-
  valor-específico, igual que la resolución de forecast/pipeline).
- **`entities/sla_instance.py`** — `SLAInstance`, el reloj de SLA de un
  caso. `record_first_response()`/`record_resolution()` son de una sola
  vez (lanzan si ya se registraron). `effective_breach_status()` implementa
  la derivación descrita arriba.
- **`policies/service_level_policy_resolver.py`** — `ServiceLevelPolicyResolver`,
  dominio puro: dada una lista de políticas activas ya cargadas, elige la
  de mayor especificidad que aplique (o `None`).
- **`events.py`** — `CustomerServiceEvents` (14 eventos) +
  `build_event_payload()` propio (mismo patrón que `CustomerEvents`/
  `CRMEvents` — un namespace de eventos por bounded context).
- **`repository_ports.py`** — puertos para los seis repositorios.
- **`exceptions.py`** — solo errores propios de este bounded context
  (`ServiceCaseNotFoundError`, `InvalidServiceCaseStateError`,
  `InvalidSLAInstanceError`, etc.) — sin duplicar los errores de
  autorización de CRM (ver arriba).

## Infraestructura

- **`backend/infrastructure/db/schema/customer_service_schema.py`** —
  archivo nuevo, 9 tablas: `service_case_categories`,
  `service_level_policies`, `service_cases`, `service_case_resolutions`,
  `service_case_escalations`, `sla_instances`,
  `customer_service_audit_log`, `customer_service_outbox`,
  `customer_service_processed_events`.
- **`migrations/standalone/186_customer_service_bounded_context_schema.py`**
  — numeración verificada contra `engine.py` y el directorio
  `migrations/standalone/` inmediatamente antes de crear el archivo (lección
  de CRM-6: otra sesión concurrente había tomado el 184; esta vez se
  verificó primero y 186 estaba libre — otra sesión tomó el 187
  *después*, sin colisión). Registrada en `migrations/engine.py`.
  Verificado contra el bootstrap completo: 564 tablas totales.
- **`backend/infrastructure/db/repositories/customer_service/`** — seis
  repositorios + `support_repositories.py` + `unit_of_work.py` +
  `base.py`, todos mirror exacto de la capa CRM equivalente.

## Aplicación (`backend/application/customer_service/`)

- **`use_cases/service_case_use_cases.py`** — `CreateServiceCaseUseCase`
  (resuelve la política de SLA aplicable vía
  `ServiceLevelPolicyResolver` y crea el `SLAInstance` en la misma
  transacción si hay una política que aplique; si no hay ninguna
  configurada, el caso se crea igual, simplemente sin SLA — no es un error),
  `UpdateServiceCaseUseCase`, `AssignServiceCaseUseCase` (split
  ASSIGN/REASSIGN, mismo patrón que CRM-5/CRM-6),
  `StartServiceCaseProgressUseCase`, `WaitForCustomerUseCase` (pausa la
  SLA), `WaitInternalUseCase`, `ResumeServiceCaseUseCase` (reanuda la SLA),
  `RecordFirstResponseUseCase`, `ResolveServiceCaseUseCase` (crea
  `ServiceCaseResolution` + `case.resolve()` + `sla.record_resolution()`
  atómicamente), `CloseServiceCaseUseCase`, `CancelServiceCaseUseCase`,
  `ReopenServiceCaseUseCase`.
- **`use_cases/escalate_service_case_use_case.py`** —
  `EscalateServiceCaseUseCase`: valida el motivo contra `EscalationReason`,
  incrementa `SLAInstance.escalation_level` si existe una SLA, transiciona
  el caso a `ESCALATED`, y registra un `ServiceCaseEscalation` inmutable.
- **`use_cases/service_level_policy_use_cases.py`** —
  `CreateServiceLevelPolicyUseCase` (`SLA_MANAGE`) y `OverrideSLAUseCase`
  (`SLA_OVERRIDE` — marca la SLA como COMPLETED manualmente con motivo
  obligatorio, mismo patrón de responsabilidad que
  `MoveOpportunityStageUseCase(override=True)` de CRM-5). A diferencia de
  `CRMStageDefinition` en CRM-5 (que se dejó sin CRUD porque el permiso no
  existía en el catálogo), aquí `SLA_MANAGE`/`SLA_OVERRIDE` **sí** existen
  desde CRM-2, así que esta fase construye sus consumidores en vez de
  dejarlos huérfanos.
- **`queries/service_case_query_service.py`** — `ServiceCaseQueryService`,
  reutiliza `CRMDataScopeResolver` + `CASE_VIEW_SCOPE_PERMISSIONS`
  directamente (los ejes OWN/TEAM ya existían para casos desde CRM-2, a
  diferencia de Actividades/Tareas/Notas en CRM-6). Enmascara casos
  `is_sensitive` salvo que el llamador tenga `CASES_VIEW_SENSITIVE` —
  mismo patrón que el enmascaramiento de notas privadas de
  `CRMNoteQueryService` (CRM-6).
- **`queries/sla_query_service.py`** — `SLAQueryService.list_breached()`/
  `list_at_risk()` — la fuente de datos para el KPI del dashboard "Casos
  fuera de SLA" que el master prompt menciona en su sección de dashboard.

## Verificación

```bash
python -m pytest tests/unit/crm/ tests/integration/crm/ tests/unit/customer_service/ tests/integration/customer_service/ tests/architecture/test_customers_crm_*.py -q
# 358 passed, 1 skipped (routes — CRM-14)
```

- 71 tests nuevos (42 unitarios de dominio — lifecycle de `CustomerServiceCase`,
  `ServiceLevelPolicy`/`ServiceLevelPolicyResolver`, derivación de
  `SLABreachStatus` en los cinco estados — y 29 de integración con SQLite
  real: repositorios, ciclo de vida completo con SLA pausada/reanudada/
  resuelta, escalamiento con historial, override de SLA, y
  enmascaramiento de casos sensibles).
- Los 22 guardrails de CRM-1 (`test_customers_crm_*.py`) se re-ejecutaron
  completos (no solo verificados vacuamente): esta es la primera vez que
  `customer_service` tiene código real bajo esos escaneos (antes era un
  paquete vacío), y los 21 activos + 1 en skip esperado siguieron en
  verde sin ningún ajuste.
- 436 tests de `tests/unit/customers/` + `tests/integration/customers/` +
  `tests/unit/crm/` + `tests/integration/crm/` +
  `tests/unit/customer_service/` + `tests/integration/customer_service/`
  pasan juntos.
- Sintaxis global limpia; bootstrap completo de migraciones verificado
  (564 tablas).

## Pendiente (próximas fases)

- **CRM-8 (Crédito):** siguiente sub-bounded-context vacío que CRM-1
  anticipó (`customer_credit`).
- **CRM-10 (Segmentación):** cuando exista, `ServiceLevelPolicy` gana un
  eje `segment_id` para el matching de SLA descrito en §30-32 y no
  implementado aquí.
- **CRM-12 (Customer 360):** el lugar natural para una vista unificada
  "caso + su historial de actividades/tareas/notas" — CRM-7 no construyó
  esa composición cruzada (mismo criterio que CRM-6 dejó explícito para
  la línea de tiempo unificada del cliente).
- **CRM-14 (UI Foundations):** activa el último guardrail en skip; también
  candidato natural para una gestión de `ServiceCaseCategory` con permiso
  propio si se detecta la necesidad (no existe un permiso dedicado en el
  catálogo de CRM-2 para administrar categorías, similar al caso de
  `CRMStageDefinition` en CRM-5).
- Extender el `resolution_due_at` de una SLA por la duración real que
  estuvo pausada — simplificación v1 documentada, no implementada.
