# CRM-5 — Oportunidades / Pipeline

Fecha: 2026-08-10. Depende de CRM-0 (auditoría), CRM-1 (guardrails), CRM-2
(seguridad — `CRMPermissions.OPPORTUNITIES_*`/`PIPELINE_VIEW`/`FORECAST_*`
ya existían, sin consumidor hasta ahora), CRM-4 (Leads —
`ConvertLeadUseCase` dejó explícitamente sin implementar la "oportunidad
opcional" de §18; CRM-5 la cierra).
Fuente de diseño: `docs/refactor/customers_crm_master_prompt.md` §19-22.
Precedente seguido: `backend/domain/crm/entities/lead.py` (CRM-4) — mismo
patrón entidad-agregada + value objects + políticas + repositorios + UoW +
casos de uso + query services, aplicado ahora a `Opportunity`.

## Objetivo

Pipeline comercial completo: `Opportunity`, el catálogo configurable de
etapas (`CRMStageDefinition`), el historial de movimientos
(`OpportunityStageHistory`), líneas de interés de producto
(`OpportunityProductInterest`), y el forecast operativo
(`SalesPipelineForecastQueryService`). Cierra el gancho que CRM-4 dejó
abierto: `CreateOpportunityFromLeadUseCase` consume el `customer_id` que
`ConvertLeadUseCase` ya devuelve en su `CRMResult.data`.

## Dominio (`backend/domain/crm/`)

- **`enums.py`** — `OpportunityStatus` (OPEN/WON/LOST/CANCELLED/ON_HOLD).
  La *etapa* dentro de OPEN es un concepto separado y configurable — ver
  `CRMStageDefinition`, nunca una rama de enum hardcodeada (§19-22: "Pipeline
  configurable... nunca hardcodeado").
- **`entities/stage_definition.py`** — `CRMStageDefinition`: catálogo de
  etapas como datos, no enum. Campos: `code`, `name`, `sequence_order`,
  `probability_default`, `is_won_stage`/`is_lost_stage` (para que
  Win/LoseOpportunityUseCase resuelvan la etapa terminal sin adivinar),
  `required_fields` (tupla de nombres de campo), `min_activities`, `active`.
  CRM-5 siembra un pipeline por defecto de 6 etapas vía la migración 183
  (ver más abajo) para que el sistema sea usable de inmediato; una
  administración de etapas con permiso propio se difiere (no existe un
  permiso `CRM.pipeline.configurar` en el catálogo de CRM-2 — inventar uno
  aquí habría sido una decisión de seguridad fuera de alcance de esta fase;
  candidato natural para CRM-14+ cuando exista la UI de administración).
- **`entities/opportunity.py`** — agregado raíz. Máquina de estados:

  ```text
  OPEN ──put_on_hold(reason)──► ON_HOLD ──resume()──► OPEN
    │                                │
    ├──win()────────────────────────┤──win()──► WON (terminal)
    ├──lose(reason)──────────────────┤──lose(reason)──► LOST (terminal)
    └──cancel(reason)────────────────┘──cancel(reason)──► CANCELLED (terminal)

  LOST/CANCELLED ──reopen(reason)──► OPEN
  ```

  `move_stage()` solo muta sus propios campos (`stage_id`/`probability`/
  `expected_close_date`) desde OPEN u ON_HOLD; no valida campos
  obligatorios, actividad mínima ni motivo de retroceso — eso es
  responsabilidad de `CRMStageTransitionPolicy`, orquestada por
  `MoveOpportunityStageUseCase` (mismo split que `Lead.convert()` /
  `ConvertLeadUseCase` en CRM-4). `win()`/`lose()` aceptan un
  `won_stage_id`/`lost_stage_id` opcional para dejar el Kanban consistente
  (la columna de etapa siempre refleja la realidad, incluidas las columnas
  cerradas).
- **`entities/opportunity_stage_history.py`** — registro inmutable de cada
  movimiento de etapa (§19-22: `OpportunityStageHistory`). `from_stage_id`
  es `None` solo en la primera entrada (la etapa asignada al crear).
- **`entities/opportunity_product_interest.py`** — líneas de interés de
  producto (§19-22: `OpportunityProductInterest`). `product_reference_id`
  es un puntero opaco al bounded context de Productos — nunca FK entre
  archivos de esquema (CRM no es dueño del catálogo de productos, misma
  decisión de bajo acoplamiento que `Lead.origin_branch_id`/`territory_id`
  en CRM-4); `product_name` es una foto denormalizada.
- **`policies/stage_transition_policy.py`** — `CRMStageTransitionPolicy`.
  No valida permiso (eso sigue siendo capa de aplicación, mismo split que
  el resto de CRM) — valida las otras cuatro cosas que pide §19-22: campos
  obligatorios (`to_stage.required_fields`, satisfechos por el valor
  propuesto o por el ya existente en la entidad), actividad mínima
  (`activities_logged_count`), motivo obligatorio al retroceder de etapa
  (`to_stage.sequence_order < from_stage.sequence_order`), y
  probabilidad/etapa-destino válidas. `override=True` (permiso
  `OPPORTUNITIES_OVERRIDE_STAGE`) omite campos obligatorios/actividad
  mínima/motivo-de-retroceso, pero **nunca** omite el motivo en sí (una
  excepción sigue siendo auditable) ni permite mover una oportunidad
  cerrada o hacia una etapa inactiva.
- **`events.py`** — `CRMEvents` extendido con el subconjunto Oportunidades
  de §77 (OPPORTUNITY_CREATED/UPDATED/ASSIGNED/STAGE_CHANGED/PUT_ON_HOLD/
  RESUMED/WON/LOST/CANCELLED/REOPENED); `build_event_payload()` ahora acepta
  `opportunity_id` además de `lead_id` (cambio compatible hacia atrás — los
  llamados existentes de CRM-4 con `lead_id=...` siguen funcionando igual).
- **`repository_ports.py`** — `OpportunityRepositoryPort`,
  `CRMStageDefinitionRepositoryPort`, `OpportunityStageHistoryRepositoryPort`,
  `OpportunityProductInterestRepositoryPort`.
- **`exceptions.py`** — `OpportunityNotFoundError`,
  `InvalidOpportunityStateError` (nombrado así, no
  `OpportunityStateInvalidError` como dice literalmente §93 — mismo criterio
  que `InvalidLeadStateError`/`InvalidCustomerStateError` en CRM-3/CRM-4:
  consistencia con el patrón ya establecido en este módulo, no una decisión
  nueva), `OpportunityStageTransitionNotAllowedError`,
  `InvalidOpportunityCodeError`, `InvalidStageDefinitionError`.

## Infraestructura

- **`backend/infrastructure/db/schema/crm_schema.py`** — se extiende (mismo
  archivo que Leads; `crm` es un solo sub-bounded-context, un solo archivo
  de esquema, misma convención de CRM-4). 4 tablas nuevas:
  `crm_stage_definitions`, `opportunities`, `opportunity_stage_history`,
  `opportunity_product_interests`. `crm_audit_log` gana una columna
  `opportunity_id` (antes solo tenía `lead_id`).
- **`migrations/standalone/183_crm_opportunities_schema.py`** — crea las 4
  tablas nuevas vía `create_crm_schema()` (idempotente, `CREATE TABLE IF NOT
  EXISTS`), agrega `crm_audit_log.opportunity_id` con `ALTER TABLE` idempotente
  (patrón de la migración 180 — `CREATE TABLE IF NOT EXISTS` no habría
  agregado la columna en una base que ya corrió la 182 antes de este cambio),
  y siembra un pipeline por defecto de 6 etapas (`INSERT OR IGNORE` por
  `code` UNIQUE, mismo patrón idempotente que la migración 169):
  Prospección → Calificación → Propuesta → Negociación → Cerrada Ganada /
  Cerrada Perdida. Registrada en `migrations/engine.py`. Verificado contra
  el bootstrap completo (`migrations.engine.up` sobre `:memory:` limpio):
  539 tablas totales (535 previas + 4 nuevas), pipeline sembrado
  correctamente.
- **`backend/infrastructure/db/repositories/crm/`** — `opportunity_repository.py`
  (save/update/get/get_by_code/get_by_operation_id/list_owned_by/
  list_open_owned_by/list_by_stage — coerción Decimal↔TEXT y date↔TEXT
  explícita, mismo patrón que `lead_repository.py`),
  `stage_definition_repository.py` (incluye `get_won_stage()`/
  `get_lost_stage()`/`get_default_initial_stage()` — las tres consultas que
  los casos de uso de cierre/creación necesitan sin tener que conocer el
  pipeline configurado), `stage_history_repository.py`,
  `product_interest_repository.py`. `support_repositories.py`
  (`CRMAuditRepository.record()`) y `unit_of_work.py`
  (`CRMUnitOfWork`) extendidos para los cuatro repositorios nuevos —
  cambios compatibles hacia atrás con las llamadas de CRM-4.

## Aplicación (`backend/application/crm/`)

- **`use_cases/opportunity_use_cases.py`** — `CreateOpportunityUseCase`
  (resuelve la etapa inicial por defecto si no se especifica una, vía
  `get_default_initial_stage()`; registra el primer
  `OpportunityStageHistory`), `UpdateOpportunityUseCase`,
  `AssignOpportunityUseCase`, `PutOpportunityOnHoldUseCase`,
  `ResumeOpportunityUseCase`, `WinOpportunityUseCase`/
  `LoseOpportunityUseCase` (resuelven automáticamente la etapa ganada/
  perdida), `CancelOpportunityUseCase`, `ReopenOpportunityUseCase`,
  `MoveOpportunityStageUseCase` (§19-22: "El Kanban no confirma etapa solo
  por arrastrar — invoca `MoveOpportunityStageUseCase`"; corre
  `CRMStageTransitionPolicy` antes de escribir nada),
  `AddOpportunityProductInterestUseCase`.

  **`AssignOpportunityUseCase` cierra un vacío que CRM-4 dejó abierto**:
  `CRMPermissions` ya definía `OPPORTUNITIES_ASSIGN` y
  `OPPORTUNITIES_REASSIGN` por separado desde CRM-2 (igual que
  `LEADS_ASSIGN`/`LEADS_REASSIGN`), y `CRM_ROLE_MATRIX`
  (`backend/application/customers/role_matrix.py`) ya los otorga por
  separado por rol — pero `AssignLeadUseCase` (CRM-4) solo usa
  `LEADS_ASSIGN` sin importar si el lead ya tenía dueño. Para Oportunidades
  se implementó correctamente: `OPPORTUNITIES_ASSIGN` si no había
  propietario previo, `OPPORTUNITIES_REASSIGN` si ya lo había. No se tocó
  `AssignLeadUseCase` (fuera de alcance de esta fase, y arriesgaría
  regresión en los 93 tests de CRM-4 sin necesidad).

- **`use_cases/create_opportunity_from_lead_use_case.py`** —
  `CreateOpportunityFromLeadUseCase`, el gancho que CRM-4 dejó explícito en
  su documentación ("probablemente un `CreateOpportunityFromLeadUseCase`
  que consume el `customer_id` del payload de `CRM_LEAD_CONVERTED`"). Es un
  caso de uso **separado**, no una modificación de `ConvertLeadUseCase`:
  el llamador ya recibe `customer_id` en el `CRMResult.data` que
  `ConvertLeadUseCase` devuelve, así que solo hace falta pasarlo junto con
  `lead_id` (para `source_lead_id`/trazabilidad). Ambos casos de uso
  comparten la misma `connection`, así que un llamador que quiera todo el
  flujo "convertir lead → crear oportunidad" atómico puede envolver ambas
  llamadas en una transacción externa (mismo patrón de conexión compartida
  que `ConvertLeadUseCase` ya usa para sus dos bounded contexts) — pero
  nada lo obliga: la oportunidad es genuinamente opcional según §18 y puede
  crearse después, por otro actor, o no crearse nunca. Valida que el lead
  esté `CONVERTED`; hereda `amount`/`expected_close_date`/`territory_id`/
  `origin_branch_id`/`owner_user_id` del lead si no se especifican
  explícitamente. Solo toca el esquema `crm` (`customer_id` es una
  referencia opaca, nunca validada por FK contra `customers`).

  Deliberadamente **no se modificó** `convert_lead_use_case.py` — su nota
  de diferimiento ("crear oportunidad opcional — no implementado aquí")
  sigue siendo exacta, y los 31 tests de integración de CRM-4 para
  `ConvertLeadUseCase` permanecen intactos y sin riesgo de regresión.

- **`queries/opportunity_directory_query_service.py`** —
  `OpportunityDirectoryQueryService`, segundo consumidor de
  `CRMDataScopeResolver` (después de `LeadDirectoryQueryService`, mismos
  ejes OWN/TEAM). `list_by_stage_for_kanban()` agrupa las oportunidades en
  alcance por `stage_id` — el lado de lectura del Kanban de `crm.pipeline`
  (§19-22).
- **`queries/sales_pipeline_forecast_query_service.py`** —
  `SalesPipelineForecastQueryService`: pipeline total, ponderado
  (`amount × probability / 100`), por etapa, cierres esperados, vencidas
  (`expected_close_date < hoy` y aún OPEN), y "sin seguimiento". Solo
  considera oportunidades OPEN — WON/LOST/CANCELLED no cuentan como
  pipeline vivo. `stagnant` ("sin seguimiento", §19-22) se aproxima como
  "sin cambios en N días" (`updated_at`) porque Actividades (CRM-6) no
  existe todavía para dar una señal real de último contacto — mismo tipo de
  parche explícito y documentado que CRM-4 usó con
  `activities_logged_count=0` en `MoveOpportunityStageUseCase`; revisar
  cuando CRM-6 aterrice.

## Verificación

```bash
python -m pytest tests/unit/crm/ tests/integration/crm/ tests/architecture/test_customers_crm_*.py -q
# 193 passed, 1 skipped (routes — CRM-14)
```

- 84 tests nuevos (44 unitarios de dominio — lifecycle de `Opportunity`,
  `OpportunityCode`, `CRMStageDefinition`, `CRMStageTransitionPolicy` con
  todas sus reglas incluyendo `override`, `OpportunityStageHistory`,
  `OpportunityProductInterest` — y 40 de integración con SQLite real:
  repositorios incluyendo el pipeline sembrado, casos de uso de ciclo de
  vida completo, movimiento de etapa con validación real, asignación/
  reasignación con permisos distintos, forecast, y
  `CreateOpportunityFromLeadUseCase` incluyendo el flujo cruzado real
  lead→cliente→oportunidad).
- Los 22 guardrails de CRM-1 siguen en verde (21 activos + 1 en skip
  esperado para CRM-14) — no requirieron ningún ajuste retroactivo esta
  vez (a diferencia de CRM-4, que tuvo que generalizar
  `CRM_SCHEMA_FILE`→`CRM_SCHEMA_FILES`; esa generalización ya cubre el
  archivo `crm_schema.py` que esta fase extiende, así que no hizo falta
  tocar los guardrails de nuevo).
- Los 271 tests de `tests/unit/customers/` + `tests/integration/customers/`
  + `tests/unit/crm/` + `tests/integration/crm/` pasan juntos (ninguna
  regresión cruzada).
- Sintaxis global limpia; bootstrap completo de migraciones verificado
  (539 tablas, mismos 3 fallos preexistentes y no relacionados en
  migraciones legacy de caja 024/029/080 que ya se documentaron en
  CRM-4).

## Pendiente (próximas fases)

- **CRM-6 (Actividades):** provee la señal real de actividad que
  `activities_logged_count` (hoy fijo en 0 en
  `MoveOpportunityStageUseCase`) y `stagnant` (hoy aproximado por
  `updated_at`) necesitan para ser precisos. Hasta entonces, cualquier
  etapa configurada con `min_activities > 0` solo es alcanzable con
  `override=True` — el pipeline sembrado por defecto usa `min_activities=0`
  en las 6 etapas precisamente para no bloquear el uso normal mientras
  tanto.
- **CRM-14 (UI Foundations):** activa el último guardrail en skip; también
  el lugar natural para una administración de `CRMStageDefinition` con
  permiso propio (ver nota en `entities/stage_definition.py` sobre por qué
  esta fase no inventó un permiso `CRM.pipeline.configurar`).
- No implementado en CRM-5 (fuera del alcance de "Oportunidades: pipeline,
  etapas, transiciones, forecast"): cotizaciones (`Opportunity → Quote`,
  §267 — es CRM-13/Quotes), automatizaciones sobre oportunidades vencidas o
  estancadas (§56, CRM-15+).
