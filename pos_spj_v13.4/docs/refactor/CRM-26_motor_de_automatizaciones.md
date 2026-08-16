# CRM-26 — Motor de automatizaciones CRM (§56)

Fecha: 2026-08-14. El usuario eligió, del refresh de CRM-0, cerrar la única
sección grande del master prompt sin ningún código: §56 (`CRMAutomationRule`/
`CRMAutomationExecution`, triggers → acciones declarativas).

## Qué se construyó

Extiende el paquete `crm` existente (no un sexto bounded context — mismo
razonamiento que CRM-10 usó para segmentación: automatizaciones orquestan
leads/oportunidades/tareas propios de CRM, y §56 vive bajo el encabezado CRM
del master prompt).

- **Dominio** (`backend/domain/crm/`): `CRMAutomationRule`
  (trigger_type/action_type/trigger_config/action_config — JSON de
  parámetros planos, nunca código ejecutable), `CRMAutomationExecution`
  (log append-only de cada disparo), enums `CRMAutomationTrigger` (10
  valores exactos del §56), `CRMAutomationAction` (7 acciones exactas),
  `CRMAutomationExecutionStatus`.
- **Aplicación** (`backend/application/crm/use_cases/automation_use_cases.py`):
  CRUD de reglas (Create/Update/Activate/Deactivate, permission-gated) +
  dos puntos de evaluación:
  - `EvaluateEventTriggerUseCase` — reactivo, sin `actor_user_id`/permiso
    en la entrada (system-triggered, mismo razonamiento que
    `sales_event_handlers.py` de CRM-13).
  - `EvaluateTimeBasedAutomationTriggersUseCase` — sweep explícito y
    llamable, NO conectado a ningún scheduler (este repo no tiene
    mecanismo de cron/job en segundo plano en ningún lado, confirmado antes
    de construir esto). Implementa LEAD_IDLE como referencia funcional
    real; los otros 6 triggers derivados quedan documentados como brecha,
    no fabricados (ver más abajo).
- **Infraestructura**: `CRMAutomationRuleRepository`/
  `CRMAutomationExecutionRepository`, wireados en `CRMUnitOfWork`. Tablas
  `crm_automation_rules`/`crm_automation_executions` agregadas a
  `crm_schema.py` (born-clean) + migración 194 (idempotente, solo llama
  `create_crm_schema()`).
- **Permisos**: 6 códigos nuevos en `CRMPermissions`
  (`AUTOMATION_RULES_VIEW/CREATE/EDIT/ACTIVATE/DEACTIVATE`,
  `AUTOMATION_EXECUTIONS_VIEW`), reflejados también en
  `core/security/permission_catalog.py["CRM"]`.
- **Wireado real, no solo declarado**: `fire_event_trigger()` se llama
  desde `CreateLeadUseCase` (LEAD_CREATED), `MoveOpportunityStageUseCase`
  (OPPORTUNITY_STAGE_CHANGED), `CreateServiceCaseUseCase` (CASE_CREATED) —
  los tres únicos triggers de §56 que son eventos de dominio reales hoy
  (ver más abajo). Envuelto en `fire_event_trigger`'s propio try/except:
  una regla rota nunca bloquea la operación real que la disparó — mismo
  patrón defensivo que el aviso de elegibilidad de CRM-21 y el bridge
  eager de CRM-25.

## Decisión de diseño: triggers reales vs. derivados

Investigación previa a escribir código confirmó: de los 10 triggers de
§56, solo 3 son eventos de dominio genuinos que este repo ya publica
(`LEAD_CREATED`, `OPPORTUNITY_STAGE_CHANGED`, `CASE_CREATED`). Los otros 7
(`LEAD_IDLE`, `OPPORTUNITY_IDLE`, `OPPORTUNITY_OVERDUE`,
`CUSTOMER_INACTIVE`, `SLA_AT_RISK`, `SLA_BREACHED`, `CREDIT_REVIEW_DUE`)
son condiciones derivadas — nada "transiciona" a esos estados, una consulta
simplemente cruza un umbral (mismo razonamiento ya documentado para
`CRMWorkItemStatus.OVERDUE`/`SLAInstance.breach_status`). Este repo no
tiene NINGÚN mecanismo de scheduler/cron en ningún módulo — confirmado
antes de construir, no asumido. En vez de fabricar un scheduler falso o
inventar un "evento" que no existe, se separaron los 10 triggers en
`EVENT_TRIGGERS`/`TIME_BASED_TRIGGERS` (`backend/domain/crm/enums.py`) y
solo se construyó un punto de entrada explícito y llamable para el segundo
grupo — quien agregue infraestructura de scheduling a esta app de
escritorio (o a un futuro componente servidor) es el llamador previsto.

## Decisión de diseño: autorización de acciones disparadas por reglas

Cada acción de una regla llama al USE CASE EXISTENTE correspondiente
(nunca SQL directo, nunca código arbitrario — cumple literalmente "No
permitir scripts arbitrarios. Usar reglas declarativas"), pero esos use
cases exigen permiso vía `CRMAuthorizationPolicy.require()`, fail-closed.
Usar un checker permisivo (`AllowAllCRMPermissionCheckerForTests`) habría
sido una regresión de seguridad real — ese checker es explícitamente
solo-para-tests en su propio docstring, y usarlo en producción es
exactamente el atajo que CRM-21 ya se negó a tomar en una situación
similar. En su lugar: `_SingleActionPermissionChecker` — otorga
EXACTAMENTE el permiso que la acción específica necesita, solo al actor
`SYSTEM_AUTOMATION` (constante bien conocida, mismo patrón que
`_WHATSAPP_BOT_ACTOR` en `api/routers/clientes.py`). Cada disparo queda
auditado dos veces: por `CRMAutomationExecution` (qué regla, qué target,
qué resultado) y por el `audit.record(actor_user_id=SYSTEM_AUTOMATION)`
del use case destino — nunca anónimo.

## Cobertura real de acciones (§56, 7 acciones)

| Acción | Estado | Detalle |
|---|---|---|
| CREATE_TASK | ✅ Real | `CreateCRMTaskUseCase`, soporta LEAD/OPPORTUNITY/CASE |
| ASSIGN_OWNER | ✅ Real (parcial) | `AssignLeadUseCase`/`AssignOpportunityUseCase`. CUSTOMER como target queda SKIPPED con motivo explícito — el propietario de Customer vive en el stack `customers`, con su propia pila de autorización; cruzarlo aquí habría sido una integración a medias bajo presión de tiempo, no algo a fabricar |
| SEND_NOTIFICATION | ✅ Real (condicional) | `CreateCRMReminderUseCase` — un CRMReminder siempre cuelga de una tarea/actividad (§25, "no tiene destino propio"), así que solo dispara si `action_config` trae `task_id` explícito; documentado, no un no-op silencioso |
| ESCALATE_CASE | ✅ Real | `EscalateServiceCaseUseCase`, solo target CASE |
| ADD_TAG | ✅ Real | `AssignCustomerTagUseCase`, solo target CUSTOMER |
| ADD_TO_SEGMENT | ✅ Real | `AddCustomerToSegmentUseCase` con `source=RULE_BASED` (encaja exacto con el vocabulario ya existente) |
| CHANGE_PRIORITY | ❌ No implementado | No existe ningún caso de uso de cambio de prioridad standalone para Lead/Opportunity en este repo hoy — brecha real, declarada (`SKIPPED` con motivo explícito), no un caso de uso nuevo fabricado bajo esta fase |

Cada ejecutor valida su propio `target_entity_type` compatible y produce
`SKIPPED` (no `FAILED`) con un motivo legible cuando la combinación
acción/target no aplica — nunca un fallo silencioso.

## Regresión real encontrada y corregida durante la verificación

La suite completa `tests/architecture/` (corrida para CRM-25 y re-verificada
aquí) mostró 85 fallas — comparado con el baseline de 83 de CRM-24. La
inmensa mayoría (test_cash_*, test_finance_bounded_context, test_settings_*,
test_losses_*, test_merma_*, test_logistics_*, etc.) son de sesiones
concurrentes tocando módulos completamente ajenos a Clientes/CRM — verificado
grep'eando la lista completa por "cliente/crm/customer/ventas/automation":
cero coincidencias.

Una sí era real, causada por CRM-25 (no CRM-26):
`tests/architecture/test_clean_birth_guardrails.py::
test_clientes_table_is_born_clean_uuid_identity` esperaba encontrar el
patrón literal `INSERT INTO clientes (id,` dentro de `api/routers/
clientes.py` — pero CRM-25 reescribió ese endpoint para delegar en
`ClienteRepository.crear()` en vez de hacer el INSERT directo. La propiedad
REGLA CERO que el test protege (todo alta de cliente mintea id con
`new_uuid()`, nunca `lastrowid`) se sigue cumpliendo — con más fuerza, no
con menos — pero el patrón textual específico ya no existe en ese archivo
porque el archivo ya no hace SQL. Corregido: se retiró `api/routers/
clientes.py` de la lista de archivos que deben mostrar el INSERT literal, y
se agregaron dos aserciones nuevas confirmando el reemplazo real
(`"INSERT INTO clientes" not in router_src` y `"ClienteRepository" in
router_src`), documentando el motivo inline.

Las otras dos fallas de ese mismo archivo
(`test_domain_code_has_no_lastrowid_identity` sobre
`meat_processing_schema.py`, `test_services_repositories_ui_do_not_create_schema`
sobre 18 archivos de schema — TODOS los `backend/infrastructure/db/schema/
*.py` del repo, no solo los de CRM) son preexistentes y sistémicas
(afectan absolutamente todos los bounded contexts con su propio archivo de
schema, patrón establecido desde CRM-3), confirmadas sin relación
verificando que `crm_schema.py` ya aparecía en esa lista antes de que esta
fase le agregara 2 tablas más — agregar más DDL a un archivo ya señalado
por el mismo motivo estructural no es una regresión nueva.

## Explícitamente fuera de alcance

- Los 6 triggers derivados restantes más allá de LEAD_IDLE
  (`OPPORTUNITY_IDLE`/`OPPORTUNITY_OVERDUE`/`CUSTOMER_INACTIVE`/
  `SLA_AT_RISK`/`SLA_BREACHED`/`CREDIT_REVIEW_DUE`) — cada uno necesita su
  propia consulta contra un bounded context distinto; duplicar una versión
  simplificada de la lógica de breach de `SLAQueryService` aquí habría
  repetido exactamente el mismo error que CRM-13 ya marcó como
  simplificación aceptada, no como precedente a repetir a ciegas.
- Wireado de un scheduler/cron real — no existe en este repo, no se
  fabricó uno.
- `CHANGE_PRIORITY` — sin caso de uso base que llamar.
- UI del catálogo de reglas (`crm.automation_rules` no es una de las 62
  rutas ya construidas en `frontend/desktop/modules/customers_crm/`) — el
  backend está completo y probado; falta la pantalla de administración.

## Verificación

```bash
python -m pytest tests/unit/crm/test_automation_rule_entity.py \
  tests/integration/crm/test_automation_rules_application.py \
  tests/integration/crm/test_automation_time_based_sweep.py -v
```
18 tests nuevos, todos pasando (7 unitarios de la entidad, 8 de integración
del motor CRUD+evaluación+wireado real, 3 del sweep temporal).

```bash
python -m pytest tests/unit/crm/ tests/integration/crm/ \
  tests/unit/customer_service/ tests/integration/customer_service/ \
  tests/architecture/test_customers_crm_*.py \
  tests/unit/customers/ tests/integration/customers/ -q
```
690 tests pasando, cero regresiones tras wireado en
`lead_use_cases.py`/`opportunity_use_cases.py`/`service_case_use_cases.py`/
`permission_catalog.py`.

Suite completa `tests/architecture/` corrida y verificada: 1 regresión real
encontrada y corregida (arriba), todas las demás confirmadas preexistentes
o de sesiones concurrentes no relacionadas.

## Pendiente (fases futuras)

- Consultas de tiempo real para los 6 triggers derivados restantes.
- `CHANGE_PRIORITY` para Lead/Opportunity (caso de uso base).
- ASSIGN_OWNER con target CUSTOMER (cruzar al stack `customers`).
- Pantalla de administración de reglas en `customers_crm`.
- Decidir mecanismo de scheduling real para el sweep temporal.
