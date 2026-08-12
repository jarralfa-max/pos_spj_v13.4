# CRM-4 — Leads

Fecha: 2026-08-10. Depende de CRM-0 (auditoría), CRM-1 (guardrails), CRM-2
(seguridad), CRM-3 (Customer Master — `ConvertLeadUseCase` escribe en su
esquema).
Fuente de diseño: `docs/refactor/customers_crm_master_prompt.md` §16-18.
Precedente seguido: `backend/domain/customers/` completo (CRM-3) — mismo
patrón entidad-agregada + value objects + políticas + repositorios + UoW +
casos de uso + query service, aplicado ahora a `Lead`.

## Objetivo

Primeras entidades del bounded context CRM (relación comercial): `Lead` y su
evidencia de calificación `LeadQualification`. Cierre del arco creación →
asignación → calificación → conversión que pedían las tres secciones del
pipeline (creación/asignación en §16, calificación en §17, conversión en
§18).

## Dominio (`backend/domain/crm/`)

- **`enums.py`** — `LeadStatus` (NEW/ASSIGNED/CONTACTED/NURTURING/QUALIFIED/
  UNQUALIFIED/CONVERTED/LOST/ARCHIVED), `LeadSource`, `LeadPriority`,
  `QualificationModel` (MANUAL/SCORE_BASED/BANT_LIKE/CUSTOM_RULE),
  `QualificationDecision`.
- **`value_objects/lead_code.py`** — `LeadCode` (folio `LEAD-NNNNNN`, mirror
  de `CustomerCode`).
- **`entities/lead.py`** — agregado raíz. Máquina de estados:

  ```text
  NEW ──assign()──► ASSIGNED ──mark_contacted()──► CONTACTED
                        │                              │
                        ├──start_nurturing()──► NURTURING ◄┘
                        │                              │
                        ├──disqualify(reason)──► UNQUALIFIED
                        ├──qualify()──► QUALIFIED ──convert()──► CONVERTED (terminal)
                        └──lose(reason)──► LOST

  UNQUALIFIED/LOST ──archive()──► ARCHIVED (terminal)
  ```

  `convert()` solo se permite desde QUALIFIED — el flujo de §18 asume
  calificación previa (§16/§17/§18 son capacidades secuenciales, no
  independientes). El método solo cambia el estado; la orquestación real
  (crear Customer/Account/Contact) vive en `ConvertLeadUseCase` porque toca
  otro bounded context.
- **`entities/lead_qualification.py`** — registro de evidencia (§17: "La
  calificación debe dejar evidencia"). `criteria` es un `dict` libre a
  propósito — el modelo MANUAL puede no necesitarlo, SCORE_BASED usa
  `score`, BANT_LIKE/CUSTOM_RULE exigen al menos un criterio.
- **`policies/qualification_policy.py`** — `LeadQualificationPolicy.decide()`.
  Una rama por `QualificationModel`, ningún umbral hardcodeado (el llamador
  pasa `score_threshold`/`min_criteria_passed`; §17 lo exige explícitamente:
  "No hardcodear una metodología única"). CUSTOM_RULE no ejecuta código
  arbitrario — el llamador ya evaluó su regla y solo entrega la decisión;
  la política exige que haya evidencia (`criteria`) igual que
  `LeadQualification.create()`.
- **`policies/duplicate_policy.py`** — `LeadDuplicatePolicy` (nombre/
  teléfono/correo). Copia deliberada de
  `CustomerDuplicatePolicy` en vez de import cruzado — Leads y Customers son
  bounded contexts separados y Lead no tiene eje RFC/legal_name.
- **`events.py`** — `CRMEvents` (subconjunto Leads de §77;
  Oportunidades/Actividades/Casos se añaden en CRM-5/6/7).
- **`repository_ports.py`** — `LeadRepositoryPort`,
  `LeadQualificationRepositoryPort`.
- **`exceptions.py`** — extendido con `LeadNotFoundError`,
  `InvalidLeadStateError`, `LeadAlreadyConvertedError`,
  `LeadQualificationFailedError`, `InvalidLeadCodeError` (§93).

## Infraestructura

- **`backend/infrastructure/db/schema/crm_schema.py`** — **archivo nuevo**,
  separado de `customers_crm_schema.py` (CRM-3). Un archivo de esquema por
  sub-bounded-context (`customers`, `crm`, y `customer_service`/
  `customer_credit`/`customer_privacy` cuando existan) — misma convención
  que `finance_schema.py`/`inventory_schema.py`/`supplier_schema.py` en el
  resto del repo; un solo archivo para los cinco agregados habría
  desdibujado exactamente las fronteras de contexto que CRM-1 existe para
  mantener nítidas. 5 tablas: `leads`, `lead_qualifications`,
  `crm_audit_log`, `crm_outbox`, `crm_processed_events`.
  `estimated_value` es `TEXT` (Decimal serializado), no `REAL`.
- **`migrations/standalone/182_crm_bounded_context_schema.py`** + registro
  en `migrations/engine.py`. Verificado contra el bootstrap completo
  (`migrations.engine.up` sobre `:memory:` limpio): las 5 tablas aparecen;
  535 tablas totales (530 previas + 5).
- **`backend/infrastructure/db/repositories/crm/`** — `base.py`,
  `lead_repository.py` (save/update/get/get_by_code/get_by_operation_id/
  find_duplicate_rows/list_owned_by/list_open — coerción Decimal↔TEXT y
  date↔TEXT explícita en `_hydrate`/`_params`),
  `lead_qualification_repository.py` (criteria como JSON),
  `support_repositories.py` (audit/outbox/processed events),
  `unit_of_work.py` (`CRMUnitOfWork`).

## Aplicación (`backend/application/crm/`)

- **`authorization.py`** — `CRMAuthorizationPolicy`, primera conexión real
  de `CRMPermissions` (CRM-2) a un caso de uso. Fail closed, mismo patrón
  que `CustomerAuthorizationPolicy` (CRM-3).
- **`use_cases/lead_use_cases.py`** — `CreateLeadUseCase` (dedupe +
  idempotencia + folio secuencial), `UpdateLeadUseCase`, `AssignLeadUseCase`
  (alta/reasignación), `MarkLeadContactedUseCase`, `StartLeadNurturingUseCase`,
  `DisqualifyLeadUseCase`, `LoseLeadUseCase`, `ArchiveLeadUseCase`,
  `QualifyLeadUseCase` (delega en `LeadQualificationPolicy`, guarda la
  evidencia y mueve el estado en la misma transacción).
- **`use_cases/convert_lead_use_case.py`** — `ConvertLeadUseCase`, el único
  punto donde Leads (CRM) y Customer Master se tocan. Sigue el flujo exacto
  de §18: valida que el lead esté QUALIFIED → busca coincidencias
  (`CustomerDuplicatePolicy` contra `customers_uow.customers.find_duplicate_rows()`)
  → selecciona (`link_to_customer_id`) o crea `Customer` → crea
  `CustomerAccount` (si hay `company_name`) y `CustomerContactPerson` (si hay
  contacto/teléfono/correo) → **oportunidad opcional: no implementada**
  (CRM-5 no existe; el evento `CRM_LEAD_CONVERTED` ya lleva `customer_id`
  en su payload para que ese futuro use case no tenga que releer el lead) →
  marca el lead CONVERTED → audita en ambos lados. El lead **nunca se
  elimina** (§18) — queda como registro CONVERTED.

  **Atomicidad cross-context**: `CustomerUnitOfWork` y `CRMUnitOfWork`
  comparten la misma conexión sqlite pero cada una comitea independientemente
  si se usan con `with`. `ConvertLeadUseCase` las construye como objetos
  planos (sin `with`) y controla `connection.commit()`/`rollback()` una sola
  vez al final — un lead convertido sin su cliente (o viceversa) sería un
  bug de integridad real, no solo una inconsistencia de diseño. Cubierto por
  `test_requires_qualified_status` (nada se escribe si la validación falla)
  y por el flujo feliz completo.
- **`queries/lead_directory_query_service.py`** — `LeadDirectoryQueryService`,
  primer consumidor real de `CRMDataScopeResolver` (CRM-2) para la familia
  Leads (ejes OWN/TEAM únicamente, por diseño de CRM-2 — ver
  `docs/refactor/CRM-2_seguridad.md`). `get_profile()` revalida el scope
  contra el lead ya cargado, igual que `CustomerProfileQueryService`.

## Ajuste retroactivo a CRM-1

`test_customers_crm_uses_decimal_for_credit.py` y
`test_customers_crm_does_not_duplicate_cxc.py` verificaban un único
`CRM_SCHEMA_FILE` (el de `customers`, el único que existía en CRM-1/CRM-3).
Con `crm_schema.py` como segundo archivo de esquema, `customers_crm_guardrails.py`
ahora expone `CRM_SCHEMA_FILES` (uno por sub-contexto) y
`existing_crm_schema_files()`; ambos tests iteran todos los que ya existen
en vez de uno fijo. `CRM_SCHEMA_FILE` (singular) se conserva como alias del
de `customers` por compatibilidad, pero nada nuevo debería depender de él.

## Verificación

```bash
python -m pytest tests/unit/crm/ tests/integration/crm/ tests/architecture/test_customers_crm_*.py -q
# 93 passed, 1 skipped (routes — CRM-14)
```

- 62 tests nuevos (31 unitarios de dominio — lifecycle, LeadCode,
  LeadQualification, LeadQualificationPolicy con sus 4 modelos,
  LeadDuplicatePolicy — y 31 de integración con SQLite real: repositorios,
  casos de uso de ciclo de vida, calificación, y **conversión de extremo a
  extremo incluyendo la atomicidad cross-context**).
- Los 22 guardrails de CRM-1 siguen en verde (21 activos + 1 en skip
  esperado para CRM-14) tras el refactor a `CRM_SCHEMA_FILES`.
- Sintaxis global limpia; bootstrap completo de migraciones verificado.

## Pendiente (próximas fases)

- **CRM-5 (Oportunidades):** `Opportunity`/`OpportunityStage`. Ahí se
  completa la parte de §18 que CRM-4 dejó explícitamente sin implementar
  ("crear oportunidad opcional" al convertir) — probablemente un
  `CreateOpportunityFromLeadUseCase` que consume el `customer_id` del
  payload de `CRM_LEAD_CONVERTED`.
- **CRM-14 (UI Foundations):** activa el último guardrail en skip.
- No implementado en CRM-4 (fuera del alcance de "Leads: creación,
  asignación, calificación, conversión"): integración con WhatsApp/POS como
  fuente automática de leads (§13 del master prompt, "una interacción
  WhatsApp puede generar... Lead" — eso es CRM-13); automatizaciones tipo
  `LEAD_IDLE`/`CRM_LEAD_CREATED` disparando tareas (§56, CRM-15+).
