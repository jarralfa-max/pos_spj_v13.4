# PROC-7 — Preparación: Procesamiento Cárnico

Estado: **DONE** (requerimientos, reservas/asignación, operarios, y el gate
de "lista para liberar"; sin catálogo de recursos/centros de trabajo — eso es
PROC-19)

## Alcance

Todo lo previo a `RELEASED` (§15): requerimientos de material con su ciclo
requerido→reservado→asignado, asignación de operarios, y el gate final que
verifica que ninguna orden pase a `READY` con requerimientos sin reservar.
"Recursos" en el sentido de §7's propio desglose PROC-7 se resuelve con los
campos `production_area_id`/`work_center_id` que `ProcessingOrder` ya tenía
desde PROC-2 (referencias, no catálogo) — el catálogo real de áreas/centros/
estaciones/equipos es PROC-19.

## Dominio nuevo

- `MaterialRequirementStatus` (§16), `OperatorRole` (§32) — `enums.py`.
- `MaterialRequirement` (`entities/material_requirement.py`): ciclo
  `REQUIRED → RESERVED → ALLOCATED → CONSUMED` (+ `CANCELLED`), cada etapa
  acumula sin exceder la anterior (`reserve()`/`allocate()`/`consume()`),
  mismo patrón de acumulador que `ProductionPlanLine` (PROC-5).
- `OperatorAssignment` (`entities/operator_assignment.py`): asignación
  simple (usuario, rol, orden, centro de trabajo opcional), `release()`.

## Esquema y persistencia

Migración **248** (`migrations/standalone/248_meat_processing_preparation_execution_schema.py`,
registrada tras la 247) añade `material_requirements` y `operator_assignments`
— la migración 187 (núcleo productivo, PROC-3) **no se tocó**; el DDL vive en
una función separada (`create_meat_processing_preparation_execution_schema`)
dentro del mismo `meat_processing_schema.py`, siguiendo el mismo criterio de
"append-only" ya aplicado en PROC-6. `MaterialRequirementRepository` y
`OperatorAssignmentRepository` se registraron en `MeatProcessingUnitOfWork`
como `uow.material_requirements`/`uow.operator_assignments`.

## Casos de uso (`backend/application/meat_processing/use_cases/preparation_use_cases.py`)

| Use Case | Permiso | Comportamiento |
|---|---|---|
| `AddMaterialRequirementUseCase` | `MATERIAL_ASSIGN` | Crea el requerimiento; si la orden está `APPROVED`, la mueve a `MATERIALS_PENDING`. Idempotente por `operation_id`. |
| `ReserveMaterialRequirementUseCase` | `MATERIAL_ASSIGN` | `requirement.reserve()`; emite `PROCESSING_MATERIAL_RESERVED`. |
| `AllocateMaterialRequirementUseCase` | `MATERIAL_ASSIGN` | `requirement.allocate()`. |
| `AssignOperatorUseCase` / `ReleaseOperatorAssignmentUseCase` | `OPERATOR_ASSIGN` / `OPERATOR_RELEASE` (nuevos) | Alta y baja de asignación; liberación idempotente. |
| `MarkProcessingOrderReadyUseCase` | `MATERIAL_ASSIGN` | Bloquea (`MATERIALS_NOT_READY`) si algún requerimiento sigue en `REQUIRED`; si no hay requerimientos, la orden pasa a `READY` trivialmente. Idempotente. |

## Permisos nuevos (extensión de PROC-1)

`OPERATOR_ASSIGN = "PRODUCCION.operario.asignar"`,
`OPERATOR_RELEASE = "PRODUCCION.operario.liberar"` — registrados en
`core/security/permission_catalog.py["PRODUCCION"]`; auto-verificado por el
test de consistencia de PROC-1.

## Tests

`tests/unit/meat_processing/test_meat_processing_preparation_execution_entities.py`
(`MaterialRequirement`/`OperatorAssignment`, compartido con PROC-8's entidades),
`tests/integration/meat_processing/test_meat_processing_preparation_execution_repositories.py`,
`tests/integration/meat_processing/test_meat_processing_preparation_use_cases.py`
(10 tests: alta con transición de orden, idempotencia, reserva→asignación,
evento en outbox, asignación/liberación de operario e idempotencia, gate
bloqueado/satisfecho/trivial/idempotente).

## Pendiente

- `MaterialAvailabilityPort` real contra Inventory (hoy `reserve()`/`allocate()`
  registran localmente lo que Procesamiento cree tener, sin consultar
  disponibilidad real) — cuando Inventory exponga esa query service.
- Sustitución de materiales (§18, `MaterialSubstitutionPolicy`) — no
  implementada; `MaterialRequirement.substitution_allowed` existe como campo
  pero ningún Use Case lo usa todavía.
- Catálogo de recursos/centros de trabajo — PROC-19.
