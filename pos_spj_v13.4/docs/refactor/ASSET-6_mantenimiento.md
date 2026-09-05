# ASSET-6 — Mantenimiento (Activos / EAM)

Ejecutado: 2026-09-02. §22-27, §66 (parcial) del prompt maestro.

## Qué se construyó

`backend/domain/assets/entities/maintenance_plan.py` — `MaintenancePlan` (plan preventivo, §23). Valida en `create()`: frecuencia `CUSTOM` exige `frequency_value`, frecuencia `METER_BASED` exige `meter_trigger`. Guardado: `pause()`/`resume()`/`deactivate()`/`reschedule()` (reprogramar un plan pausado falla).

`backend/domain/assets/entities/maintenance_work_order.py` — `MaintenanceWorkOrder` (§24-25), la entidad más grande de esta fase. Máquina de estados completa:

```text
DRAFT → REQUESTED → APPROVED → SCHEDULED → ASSIGNED → IN_PROGRESS
                                              IN_PROGRESS ↔ PAUSED
                                              IN_PROGRESS → WAITING_PARTS | WAITING_PROVIDER → IN_PROGRESS
                    IN_PROGRESS | WAITING_PARTS | WAITING_PROVIDER → COMPLETED → CLOSED
                    cualquier estado no terminal → CANCELLED
```

`assign()` determina `provider_type` automáticamente (INTERNAL si `employee_id`, EXTERNAL si `supplier_id` — §27, nunca un string libre "Proveedor: Taller X"). `version` incrementa en cada transición (concurrencia optimista).

Nuevos enums: `MaintenanceType` (PREVENTIVE/CORRECTIVE/PREDICTIVE_FUTURE/INSPECTION/CALIBRATION/SAFETY/WARRANTY/EMERGENCY), `MaintenanceFrequencyType`, `MaintenancePlanStatus`, `MaintenanceProviderType`, `MaintenanceWorkOrderStatus`. Excepciones: `MaintenancePlanNotFoundError`, `MaintenanceWorkOrderNotFoundError`, `MaintenanceStateInvalidError`, `MaintenanceCostInvalidError`. Eventos agregados: `MAINTENANCE_PLAN_UPDATED`, `MAINTENANCE_WORK_ORDER_ASSIGNED`, `MAINTENANCE_RESUMED`, `MAINTENANCE_CANCELLED` (extienden el set de §87 igual que en ASSET-5, siguiendo los estados que sí describen §25). Ports: `MaintenancePlanRepositoryPort`, `MaintenanceWorkOrderRepositoryPort`.

## La regla que justifica todo este bounded context

`complete(actual_cost, resolution, ...)` **solo registra evidencia** — nunca llama a Finanzas ni a Tesorería. Esto es exactamente lo opuesto del legacy `core/services/asset_service.py::completar_y_pagar_mantenimiento()`, que combinaba completar la orden **y** pagarla en una sola llamada a `treasury_service.registrar_gasto_opex()`. Publicar `MAINTENANCE_COST_CONFIRMED` para que Finance/AP decida OPEX vs CAPEX es responsabilidad de la capa de aplicación (use case, fase posterior), no de la entidad.

Verificado en tres capas:
1. Los 3 guardrails de arquitectura de ASSET-1 (`test_assets_do_not_post_journal_entries.py`, `test_assets_do_not_execute_treasury_payments.py`, `test_assets_maintenance_does_not_write_finance.py`).
2. Un test unitario explícito (`test_complete_never_touches_finance_or_treasury`) que recorre `dir(wo)` y falla si algún atributo/método contiene "asiento"/"treasury"/"posting".
3. Lectura manual del código — `complete()` no importa ni referencia nada de `backend.domain.finance` ni `backend.application.finance`.

## Explícitamente fuera de alcance

Use cases de aplicación (`CreateMaintenancePlanUseCase`, `GenerateMaintenanceWorkOrderUseCase`, `CompleteMaintenanceWorkOrderUseCase`, etc. — §66) no construidos. `MaintenanceExecution`/`MaintenanceTask`/`MaintenanceResource` (mencionados en §22 como sub-conceptos) no se modelaron como entidades separadas — se consideró que los campos ya presentes en `MaintenanceWorkOrder` (resolution, root_cause, downtime_minutes, actual_cost) cubren la evidencia operativa mínima; tareas/recursos granulares quedan para si una fase de UI/reporting los necesita.

## Tests

`tests/unit/assets/test_maintenance_plan_and_work_order.py` — plan (frecuencias inválidas, pausa/reanuda/desactiva, reprogramar plan pausado falla), work order (ciclo interno completo, asignación externa cambia provider_type, pausa/reanuda, espera por refacciones, `complete()` exige resolución no vacía, completar desde DRAFT falla, cancelar dos veces falla, versión incrementa, el check de "nunca toca finanzas").

**Conteo total de la suite de Activos tras ASSET-1 a ASSET-6**: 50 tests unitarios (`tests/unit/assets/`) + 27 tests de arquitectura con 2 skips intencionales (`tests/architecture/test_assets*.py` + `test_asset_*.py`) — 77 passed, 2 skipped, todo en verde. `tests/architecture/` completo verificado sin regresiones nuevas (84 fallas preexistentes no relacionadas).

## Siguiente fase

Ninguna de las fases ASSET-3 a ASSET-6 tiene infraestructura de persistencia todavía (repository ports son solo `Protocol`, sin `assets_schema.py`, sin repos SQLite concretos, sin `use_cases`/UoW de aplicación) — nada de esto corre end-to-end contra una base de datos real. Antes de seguir apilando más dominio (ASSET-7 inspecciones, ASSET-8 medidores, ...) conviene una fase de infraestructura/persistencia que haga ejecutable lo ya construido.
