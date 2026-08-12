# PROC-5 — Planeación: Procesamiento Cárnico

Estado: **DONE** (dominio puro: `ProductionPlan`, fuentes, capacidad,
conversión a órdenes; sin infraestructura ni Use Cases todavía — mismo
alcance que PROC-2, análogo a cómo PROC-3 llegó después para persistir el
núcleo productivo)

## Alcance

`ProductionPlan`/`ProductionPlanLine` (§11), el catálogo de fuentes de
demanda, una validación básica de capacidad (§33) y el mecanismo de dominio
para convertir una línea de plan en una o más `ProcessingOrder` reales (§11:
"El plan no mueve inventario" — solo expresa demanda y rastrea su conversión).

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `backend/domain/meat_processing/enums.py` | `PlanSourceType` (`MANUAL`, `FORECAST`, `CUSTOMER_ORDER`, `MINIMUM_STOCK`, `REPLENISHMENT`, `SALES_PLAN`, `REWORK`, `INTERNAL_REQUIREMENT` — §11 "Fuentes") y `ProductionPlanStatus` (`DRAFT`→`GENERATED`→`UNDER_REVIEW`→`APPROVED`→`PARTIALLY_CONVERTED`/`CONVERTED`, más `CANCELLED`). |
| `backend/domain/meat_processing/entities/production_plan_line.py` | `ProductionPlanLine` — `planned_quantity`/`planned_weight` (demanda) vs. `converted_quantity`/`converted_weight` (cuánto ya se convirtió) + `converted_processing_order_ids` (qué órdenes se generaron). `record_conversion()` es la única forma de avanzar el rastreo; rechaza exceder lo planeado en cualquiera de las dos dimensiones. |
| `backend/domain/meat_processing/entities/production_plan.py` | `ProductionPlan` (aggregate root) — `add_line()` (solo `DRAFT`/`GENERATED`), `generate()`, `submit_for_review()`, `approve()` (segregación: aprobador ≠ creador, mismo patrón que `ProcessingOrder`), `cancel()`, y `convert_line()` — delega en la línea y luego recalcula el estado del plan (`PARTIALLY_CONVERTED` si algunas líneas tienen conversión, `CONVERTED` si todas están completas). |
| `backend/domain/meat_processing/services/capacity_validation_service.py` | `CapacityValidationService.validate(lines, *, capacity_limit, basis="weight"\|"quantity")` → `CapacityCheckResult` (`planned_load`, `within_capacity`, `overage`, `utilization_pct`). Capacidad básica configurable sin modelar centros de trabajo/turnos (eso es PROC-19) — el límite siempre lo provee el llamador, nunca hardcodeado. |

`MeatProcessingEvents` (PROC-2) se amplió con `PRODUCTION_PLAN_CREATED` y
`PRODUCTION_PLAN_APPROVED` (los dos que el prompt maestro §60 nombra
explícitamente para el plan) más `PRODUCTION_PLAN_CANCELLED`,
`PRODUCTION_PLAN_LINE_CONVERTED` y `PRODUCTION_PLAN_CONVERTED` — simétricos a
los que ya existían para `ProcessingOrder`. No se añadieron eventos para
`GENERATED`/`UNDER_REVIEW` (transiciones internas sin consumidor cross-módulo
todavía; añadirlos cuando exista uno real es barato).

## Decisión de diseño: sin invariante "debe iniciar en DRAFT"

A diferencia de la primera versión de PROC-2 (corregida en PROC-3), `ProductionPlan`
y `ProductionPlanLine` **nunca tuvieron** un guard de "debe iniciar en estado
fresco" en `__post_init__`. La lección de PROC-3 (ver `PROC-3_schema.md`) se
aplicó desde el diseño: cuando exista persistencia para planeación, un
repositorio deberá poder reconstruir un `ProductionPlan` ya `APPROVED` o
`PARTIALLY_CONVERTED` directamente desde una fila, igual que
`ProcessingOrderRepository.get()`. El estado inicial correcto (`DRAFT`) sigue
garantizado por el default del dataclass para cualquier Use Case de creación
que no pase `status=` explícitamente.

## Conversión a órdenes — el enlace con PROC-2

`ProcessingOrder` (PROC-2) ya tenía `source_type: str | None` y
`source_reference_id: str | None` — construidos precisamente para este uso:
un futuro `CreateProcessingOrderFromPlanLineUseCase` (PROC-6+) creará la
`ProcessingOrder` con `source_type="PRODUCTION_PLAN"` y
`source_reference_id=<production_plan_line_id>`, y llamará
`ProductionPlan.convert_line(line_id, processing_order_id=<nueva orden>.id, …)`
en la misma transacción de aplicación. Esta fase solo deja lista la mitad de
dominio de ese contrato — el Use Case real (orquestación + persistencia
atómica de ambos agregados) es trabajo de PROC-6.

## Auditoría REGLA CERO

| Regla | Verificación |
|---|---|
| UUIDv7 / Decimal-only | Mismos helpers de `entities/_validation.py` que el resto de PROC-2; `ProductionPlanLine` rechaza `float` explícitamente (ver `test_line_rejects_float`). |
| Sin invariante que bloquee rehidratación | Confirmado por diseño (ver arriba) — no hay test de "debe iniciar en X" que remover más adelante. |
| Sin capacidad hardcodeada | `CapacityValidationService.validate()` exige `capacity_limit` como argumento; sin constante de módulo. |

## Tests

`tests/unit/meat_processing/test_meat_processing_production_plan.py` (línea:
acumulación de conversión, rechazo de exceso, conversión parcial, idempotencia
de `processing_order_id` repetido; plan: ciclo de vida completo, transición
ilegal, segregación aprobador≠creador, bloqueo de edición tras enviar a
revisión, recálculo de estado `PARTIALLY_CONVERTED`→`CONVERTED`, conversión
antes de aprobar rechazada, línea desconocida rechazada, cancelación desde
cualquier estado no terminal), `test_meat_processing_capacity_validation.py`
(suma por peso/cantidad, detección de sobrecapacidad, `utilization_pct`,
límite negativo rechazado, basis desconocido rechazado, límite cero sin
división por cero). `test_meat_processing_events.py` amplió su cobertura del
catálogo canónico con los 5 eventos nuevos.

## Pendiente

- Persistencia (`production_plans`/`production_plan_lines` en un futuro
  `backend/infrastructure/db/schema/meat_processing_schema.py` ampliado +
  repositorios + registro en `MeatProcessingUnitOfWork`) — próxima fase de
  esquema, análoga a PROC-3.
- `CreateProcessingOrderFromPlanLineUseCase` y el resto de la orquestación de
  aplicación — PROC-6+.
- `MaterialRequirementsService`/`RecipeSnapshotService` y las demás piezas de
  `domain/meat_processing/services/` que el prompt maestro §8 lista — se
  añaden conforme las fases que las necesitan (PROC-7 en adelante) las
  requieran, seguiendo el mismo criterio de "sin scaffolding sin consumidor"
  aplicado en `events.py`.
