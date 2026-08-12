# CRM-6 — Actividades / Agenda / Tareas / Notas / Recordatorios

Fecha: 2026-08-12. Depende de CRM-0 (auditoría), CRM-1 (guardrails), CRM-2
(seguridad — `CRMPermissions.ACTIVITIES_*`/`TASKS_*`/`NOTES_*` ya existían,
sin consumidor hasta ahora), CRM-4 (Leads), CRM-5 (Opportunities) — las
actividades/tareas/notas de esta fase se enlazan a leads/oportunidades/
clientes ya construidos por esas fases.
Fuente de diseño: `docs/refactor/customers_crm_master_prompt.md` §23-26.
Precedente seguido: `backend/domain/crm/entities/opportunity.py` (CRM-5) —
mismo patrón entidad-agregada + repositorios + UoW + casos de uso + query
services, aplicado ahora a `CRMActivity`/`CRMTask`/`CRMNote`/`CRMReminder`.

## Objetivo

Agenda comercial: registro de interacciones (`CRMActivity`), tareas
accionables con fecha límite (`CRMTask`), notas de texto libre
(`CRMNote`), y recordatorios (`CRMReminder`). Cierra la brecha de
seguimiento que Leads/Oportunidades dejaron abierta — hasta ahora ningún
lead/oportunidad tenía dónde registrar "llamé al cliente" o "pendiente
enviar cotización".

## Decisiones de alcance (documentadas, no adivinadas)

- **Vínculo polimórfico, no cuatro FKs por entidad.** `CRMActivity`/
  `CRMTask`/`CRMNote`/`CRMReminder` usan un par
  `(related_entity_type, related_entity_id)` — `CRMRelatedEntityType`
  (`LEAD`/`OPPORTUNITY`/`CUSTOMER`/`CASE`) en vez de cuatro columnas
  nullable. `CASE` existe en el enum desde ya (CRM-7 no lo usa todavía)
  para que esa fase no tenga que ensanchar un CHECK constraint después.
- **`TASK`/`NOTE` no son valores de `CRMActivityType`.** §23-26 los lista
  en la misma frase que CALL/MEETING/etc., pero como `CRMTask`/`CRMNote`
  ya son entidades propias con su propio ciclo de vida y permisos,
  incluirlos como *tipos* de actividad habría desdibujado exactamente esa
  frontera — mismo criterio que las decisiones de nomenclatura de CRM-2/
  CRM-3 (`InvalidLeadStateError` en vez de `LeadStateInvalidError`, etc.).
- **OVERDUE nunca se persiste.** `CRMWorkItemStatus.OVERDUE` existe como
  valor del enum (para que la capa de consulta/UI tenga un nombre
  canónico — §23-26: "Vencida se muestra con estado+icono, no solo
  color") pero la columna `status` en base de datos solo admite
  PLANNED/IN_PROGRESS/COMPLETED/CANCELLED. `effective_status()` en
  `CRMActivity`/`CRMTask` calcula OVERDUE comparando `scheduled_at`/
  `due_at` contra "ahora" en el momento de la consulta — nada transiciona
  un registro a OVERDUE, así que no hace falta un job en segundo plano
  para mantener la columna honesta.
- **`CRMTask` no tiene IN_PROGRESS.** §23-26 no describe una acción
  "iniciar tarea" (solo crear/completar/reprogramar/asignar/cancelar) —
  agregar un estado sin caso de uso que lo dispare habría sido
  espectulativo. `CRMActivity` sí tiene IN_PROGRESS porque `StartCRM
  ActivityUseCase` es una acción real (registrar que una llamada ya
  empezó).
- **`CRMInteraction` no se implementa.** La mención de una entidad
  separada en §23-26 es de una sola línea, sin campos/ciclo de vida/
  permisos propios distinguibles de `CRMActivity` — una llamada/email/
  WhatsApp ya completado (`CRMActivity` en estado COMPLETED) *es* un
  registro de interacción. Crear una tabla paralela sin un campo que la
  diferencie habría sido dos tablas para el mismo concepto. Si CRM-13
  (integración WhatsApp/POS) necesita un log inmutable de touchpoints
  entrantes/salientes distinto de las actividades planeables, se
  construye entonces con requisitos reales.
- **Notas sin eje OWN/TEAM.** `NOTES_EDIT_OWN`/`NOTES_DELETE_OWN` son
  invariantes duros verificados en el caso de uso (`note.is_authored_by
  (actor_user_id)`), no un filtro de alcance — CRM-2 nunca definió un eje
  TEAM/COMPANY para notas (a diferencia de leads/oportunidades/casos), así
  que esta fase no inventa uno.

## Dominio (`backend/domain/crm/`)

- **`enums.py`** — `CRMRelatedEntityType`, `CRMActivityType`,
  `CRMWorkItemStatus` (compartido entre Activity/Task), `ReminderChannel`
  (IN_APP/EMAIL/WHATSAPP_INTERNAL/PUSH_FUTURE).
- **`entities/crm_activity.py`** — `CRMActivity`. Máquina de estados:
  `PLANNED → start() → IN_PROGRESS → complete() → COMPLETED` (o
  `complete()` directo desde PLANNED), `cancel(reason)` desde PLANNED/
  IN_PROGRESS, `reschedule()`, `reassign()`.
- **`entities/crm_task.py`** — `CRMTask`. `due_at` obligatorio (una tarea
  sin fecha límite no es accionable). `complete()`/`cancel(reason)`/
  `reschedule()`/`assign()`, todas solo desde PLANNED.
- **`entities/crm_note.py`** — `CRMNote`. Sin `status` (es texto, no
  planificable). `edit()` + `is_authored_by()` (la aplicación decide qué
  hacer con eso).
- **`entities/crm_reminder.py`** — `CRMReminder`. Solo construcción — sin
  `mark_sent()` ni ciclo de vida propio (§26: "CRM solo define
  recordatorio/destinatario"; el envío es de Notification Management).
  Requiere `task_id` XOR `activity_id` (nunca ninguno, nunca ambos).
- **`events.py`** — extendido con el subconjunto Activities/Tasks/Notes/
  Reminders de §77 (16 eventos nuevos); `build_event_payload()` ya
  soportaba **extra desde CRM-4, así que no necesitó cambios de firma —
  `activity_id`/`task_id`/`note_id`/`reminder_id` se pasan como kwargs
  sueltos.
- **`repository_ports.py`** — `CRMActivityRepositoryPort`,
  `CRMTaskRepositoryPort`, `CRMNoteRepositoryPort`,
  `CRMReminderRepositoryPort`.
- **`exceptions.py`** — `CRMActivityNotFoundError`,
  `InvalidCRMActivityStateError`, `CRMTaskNotFoundError`,
  `InvalidCRMTaskStateError`, `CRMNoteNotFoundError`,
  `InvalidCRMNoteError`, `InvalidCRMReminderError`.

## Ajuste retroactivo a CRM-2

Dos permisos que ninguna entidad anterior necesitaba, agregados a
`CRMPermissions` + `core/security/permission_catalog.py["CRM"]` (mismo
precedente que `CustomerPermissions.DEACTIVATE` en CRM-3):

- **`TASKS_RESCHEDULE`** (`CRM.tareas.reprogramar`) — §23-26 nombra
  `RescheduleCRMTaskUseCase` explícitamente, pero el catálogo original de
  CRM-2 no tenía un permiso de "reprogramar" distinto de asignar/
  completar/cancelar. Reusar `TASKS_ASSIGN` habría sido un desajuste
  semántico.
- **`REMINDERS_CREATE`** (`CRM.recordatorios.crear`) — `CRMReminder`
  no tenía ningún permiso asociado en el catálogo original.

Verificado 1:1 sin drift: `ALL_CRM_PERMISSIONS` (código) ==
`CANONICAL_MODULE_PERMISSIONS["CRM"]` (catálogo), 80 permisos totales
(78 → 80).

## Infraestructura

- **`backend/infrastructure/db/schema/crm_schema.py`** — se extiende
  (mismo archivo que Leads/Oportunidades; `crm` sigue siendo un solo sub-
  bounded-context). 4 tablas nuevas: `crm_activities`, `crm_tasks`,
  `crm_notes`, `crm_reminders`. `crm_audit_log` gana `activity_id`/
  `task_id`/`note_id` (antes solo tenía `lead_id`/`opportunity_id`).
- **`migrations/standalone/185_crm_activities_schema.py`** — numerada
  **185, no 184**: el número 184 ya estaba tomado por
  `184_inventory_cold_chain_resolution.py` (un cambio no relacionado de
  Inventario que aterrizó mientras esta fase estaba en curso) — se
  renumeró al siguiente slot libre en vez de colisionar. Crea las 4 tablas
  nuevas vía `create_crm_schema()` (idempotente), agrega las 3 columnas de
  `crm_audit_log` con `ALTER TABLE` idempotente (patrón de las
  migraciones 180/183). Registrada en `migrations/engine.py` después de
  la 184 de Inventario. Verificado contra el bootstrap completo: 543
  tablas totales (539 previas + 4 nuevas).
- **`backend/infrastructure/db/repositories/crm/`** —
  `activity_repository.py`, `task_repository.py` (incluye `list_open()`
  para un futuro dispatcher de recordatorios/vencidas), `note_repository.py`
  (incluye `delete()` — la única entidad CRM con borrado físico, porque
  una nota mal escrita no necesita quedar en el historial como sí lo
  necesita un lead/oportunidad/tarea), `reminder_repository.py`.
  `support_repositories.py` (`CRMAuditRepository.record()`) y
  `unit_of_work.py` extendidos — cambios compatibles hacia atrás.

## Aplicación (`backend/application/crm/`)

- **`use_cases/activity_use_cases.py`** — `CreateCRMActivityUseCase`,
  `StartCRMActivityUseCase`, `CompleteCRMActivityUseCase`,
  `CancelCRMActivityUseCase`, `RescheduleCRMActivityUseCase`,
  `ReassignCRMActivityUseCase`.
- **`use_cases/task_use_cases.py`** — los cinco nombrados literalmente en
  §23-26: `CreateCRMTaskUseCase`, `CompleteCRMTaskUseCase`,
  `RescheduleCRMTaskUseCase`, `AssignCRMTaskUseCase`,
  `CancelCRMTaskUseCase`. `AssignCRMTaskUseCase` aplica el mismo patrón
  ASSIGN-vs-REASSIGN que `AssignOpportunityUseCase` (CRM-5): permiso
  `TASKS_ASSIGN` si la tarea no tenía asignado previo, `TASKS_REASSIGN` si
  ya lo tenía.
- **`use_cases/note_use_cases.py`** — `CreateCRMNoteUseCase` (elige
  `NOTES_CREATE` o `NOTES_CREATE_PRIVATE` según `is_private`),
  `UpdateCRMNoteUseCase`/`DeleteCRMNoteUseCase` (permiso + verificación de
  autoría — ver "Decisiones de alcance").
- **`use_cases/reminder_use_cases.py`** — solo `CreateCRMReminderUseCase`
  (ver "Decisiones de alcance": sin lifecycle de envío).
- **`queries/crm_activity_query_service.py`**,
  **`queries/crm_task_query_service.py`** — sin `CRMDataScopeResolver`:
  CRM-2 solo definió un permiso plano `ACTIVITIES_VIEW`/`TASKS_VIEW` para
  esta familia (a diferencia de leads/oportunidades/casos, que sí tienen
  eje `ver.propia`/`ver.equipo`), así que esta fase no inventa un eje que
  el catálogo nunca tuvo — alcanzar una actividad/tarea específica en la
  UI ya pasó por el query service con alcance de su entidad padre
  (Lead/Opportunity). `list_overdue_for()` en ambos expone OVERDUE vía
  `effective_status()`.
- **`queries/crm_note_query_service.py`** — enmascara notas privadas:
  una nota `is_private` se oculta de la lista salvo que el llamador tenga
  `NOTES_VIEW_PRIVATE` **o** sea su propio autor.

## Verificación

```bash
python -m pytest tests/unit/crm/ tests/integration/crm/ tests/architecture/test_customers_crm_*.py -q
# 272 passed, 1 skipped (routes — CRM-14)
```

- 79 tests nuevos (35 unitarios de dominio — lifecycle de las 4 entidades,
  incluida la derivación de OVERDUE en `effective_status()` — y 44 de
  integración con SQLite real: repositorios, casos de uso completos,
  enmascaramiento de notas privadas, y el split ASSIGN/REASSIGN de
  tareas).
- Los 22 guardrails de CRM-1 siguen en verde sin ajuste retroactivo
  (mismo archivo de esquema, ya cubierto por `CRM_SCHEMA_FILES` desde
  CRM-4).
- 350 tests de `tests/unit/customers/` + `tests/integration/customers/` +
  `tests/unit/crm/` + `tests/integration/crm/` pasan juntos.
- Sintaxis global limpia; bootstrap completo de migraciones verificado
  (543 tablas).

## Hallazgo fuera de alcance (reportado, no corregido en esta fase)

Al correr `tests/architecture/` completo (no solo los guardrails de
`customers_crm`) como verificación cruzada extra, aparecieron 74 fallas
preexistentes y no relacionadas con CRM — abarcan Settings, Transfers,
Refactor Orchestrator, Productos, Procurement, y (relevante de notar)
`test_text_pk_not_null.py`: 287 de 525 tablas TEXT-PK en todo el esquema
(prácticamente todos los bounded contexts existentes, incluidas `customers`
y `accounts` de fases previas) carecen de `NOT NULL` explícito en su
columna PK — una brecha real de "Fase G" que **no** es específica de CRM ni
de esta sesión. Las tablas nuevas de CRM-4/5/6 siguen exactamente la misma
convención `id TEXT PRIMARY KEY` que el 100% del resto del código base
existente; corregir solo las tablas de CRM sin tocar las otras ~270 no
haría pasar el guardrail y sería inconsistente con el resto del esquema.
Queda fuera del pipeline CRM-0..23 — se documenta aquí para que quede
registrado, no para que se resuelva en este phase.

## Pendiente (próximas fases)

- **CRM-7 (Atención al cliente / Casos):** primer consumidor real de
  `CRMRelatedEntityType.CASE`.
- **CRM-14 (UI Foundations):** activa el último guardrail en skip.
- No implementado en CRM-6: dispatcher real de recordatorios (Notification
  Management no existe como integración todavía — `CRMReminder` solo
  queda persistido); actividad automática desde WhatsApp/POS (CRM-13);
  `activities_logged_count` real para `CRMStageTransitionPolicy` (CRM-5) —
  ahora que `CRMTaskRepository`/`CRMActivityRepository` existen,
  `MoveOpportunityStageUseCase` podría contarlas por
  `related_entity_id=opportunity_id`, pero cablear esa integración es un
  cambio a código de CRM-5, deliberadamente fuera del alcance de "CRM-6:
  actividades, tareas, notas".
