# PROC-8 — Ejecución: Procesamiento Cárnico

Estado: **DONE** (inicio, pausa, reanudación, steps, incidencias — ambos con
Use Cases reales sobre las entidades ya construidas en PROC-2)

## Alcance

`ProcessExecution` (start/pause/resume/complete) ya existía completo desde
PROC-2 — PROC-8 es, sobre todo, la primera capa de **aplicación** que lo
orquesta junto con la orden (`ProcessingOrder.start()/pause()/resume()/complete()`),
más dos entidades nuevas: `ProcessStepExecution` (§20, sub-pasos dentro de una
ejecución) y `ProcessIncident` (§30).

## Dominio nuevo

- `IncidentType`, `IncidentStatus` (§30) — `enums.py`.
- `ProcessStepExecution` (`entities/process_step_execution.py`): más simple
  que `ProcessExecution` (sin pausa/reanudación — un paso es una unidad
  atómica corta): `NOT_STARTED → ACTIVE → COMPLETED` (+ `CANCELLED`).
- `ProcessIncident` (`entities/process_incident.py`): `OPEN → UNDER_REVIEW →
  RESOLVED → CLOSED`, puede resolverse directo desde `OPEN`. Solo su propio
  ciclo de vida — los efectos cruzados que describe §30 (bloquear outputs,
  abrir mantenimiento, abrir merma, solicitar calidad, generar alerta) se
  orquestan a nivel de aplicación cuando esos módulos existan (PROC-15/16/20);
  esta fase implementa el único que sí tiene sentido hoy: pausar la orden.

## Esquema

Mismas 4 tablas de la migración 248 que PROC-7 (`process_step_executions`,
`process_incidents`) — ver `PROC-7_preparation.md` para el detalle de la
migración. `ProcessStepExecutionRepository`/`ProcessIncidentRepository`
registrados en `MeatProcessingUnitOfWork` como `uow.steps`/`uow.incidents`.

## Casos de uso (`backend/application/meat_processing/use_cases/execution_use_cases.py`)

| Use Case | Permiso | Comportamiento |
|---|---|---|
| `StartProcessExecutionUseCase` | `ORDER_START` | Crea+arranca una `ProcessExecution` **y** llama `order.start()` (`RELEASED→IN_PROGRESS`) en la misma transacción; emite `PROCESSING_ORDER_STARTED`. Idempotente. |
| `PauseProcessExecutionUseCase` / `ResumeProcessExecutionUseCase` | `ORDER_PAUSE` / `ORDER_RESUME` | Pausan/reanudan la ejecución **y** la orden juntas; emiten `PROCESSING_ORDER_PAUSED`/`_RESUMED`. Idempotentes. |
| `CompleteProcessExecutionUseCase` | `ORDER_COMPLETE` | Completa la ejecución (si existe) y la orden; emite `PROCESSING_ORDER_COMPLETED`. |
| `StartProcessStepUseCase` / `CompleteProcessStepUseCase` | `ORDER_START` / `ORDER_COMPLETE` | Sub-pasos dentro de una ejecución ya iniciada. |
| `ReportProcessIncidentUseCase` | `INCIDENT_REPORT` (nuevo) | Registra la incidencia; `pause_order=True` pausa ejecución+orden en la misma llamada — evita una segunda transacción para el efecto más común de §30. Emite `PROCESSING_INCIDENT_REPORTED`. |
| `ResolveProcessIncidentUseCase` | `INCIDENT_RESOLVE` (nuevo) | `incident.resolve()`. Idempotente. |

Se buscan ejecuciones "actuales" vía `_current_execution()` (la última no
terminal para la orden) — este modelo simple asume una sola ejecución activa
por orden a la vez; si en una fase futura una orden necesita ejecuciones
paralelas (p. ej. por lote), este helper es el punto a extender.

## Permisos nuevos (extensión de PROC-1)

`INCIDENT_REPORT = "PRODUCCION.incidencia.reportar"`,
`INCIDENT_RESOLVE = "PRODUCCION.incidencia.resolver"` — registrados en el
catálogo canónico junto con los de PROC-7.

## Evento nuevo

`PROCESSING_INCIDENT_REPORTED` (§60) añadido a `MeatProcessingEvents`.

## Refactor de soporte: helpers compartidos entre Use Cases

Al escribir el tercer módulo de Use Cases se extrajo `_fail()`/`_scope_fail()`
(antes duplicados en `processing_order_use_cases.py`, PROC-6) a
`use_cases/_shared.py`; `processing_order_use_cases.py` se actualizó para
importarlos en vez de redefinirlos. El test de arquitectura
`test_meat_processing_use_cases_are_authorized.py` (PROC-6) se ajustó para
excluir `_shared.py` (no es una clase de Use Case: no autoriza ni abre un
`MeatProcessingUnitOfWork` por sí mismo).

## Tests

`tests/unit/meat_processing/test_meat_processing_preparation_execution_entities.py`
(`ProcessStepExecution`/`ProcessIncident`),
`tests/integration/meat_processing/test_meat_processing_preparation_execution_repositories.py`,
`tests/integration/meat_processing/test_meat_processing_execution_use_cases.py`
(10 tests: inicio/idempotencia, pausa↔reanudación, pausa sin ejecución activa,
completar orden+ejecución, paso iniciar/completar, paso desconocido, incidencia
con y sin pausar, resolución+idempotencia).

## Pendiente

- Efectos cruzados de una incidencia además de pausar (bloquear outputs, abrir
  mantenimiento, abrir merma, solicitar calidad, alerta) — PROC-15/16/20.
- Ejecuciones concurrentes por lote (`processing_batch_id`) si algún proceso
  real lo requiere — el campo ya existe en `ProcessExecution` desde PROC-2,
  pero `_current_execution()` no lo usa todavía para desambiguar.
