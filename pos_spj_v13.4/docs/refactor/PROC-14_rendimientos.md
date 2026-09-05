# PROC-14 — Rendimientos: Procesamiento Cárnico

Estado: **DONE** (esperado/real/tolerancias ya existían desde PROC-2;
esta fase añade la conciliación **desacoplada** de la captura y la
aprobación — el `YieldReconciliation.approve()` de PROC-2 no tenía llamador
hasta ahora)

## Alcance

`YieldReconciliation` + `YieldReconciliationPolicy` (esperado, real,
tolerancias, clasificación) son de PROC-2; `RecordProcessOutputsUseCase`
(PROC-11/12) ya las usa, pero solo dentro de la captura atómica de outputs.
PROC-14 cubre el caso que faltaba: reconciliar el rendimiento de una orden
cuyos outputs se capturaron **incrementalmente** (uno a uno, vía
`CaptureProcessOutputUseCase`, PROC-10) — y cerrar el ciclo de vida de la
conciliación con su aprobación.

## Refactor de soporte

La suma de outputs por tipo (`MAIN_PRODUCT`/`CO_PRODUCT`/`BY_PRODUCT`/
`WASTE`+`LOSS`) estaba escrita en línea dentro de `RecordProcessOutputsUseCase`
(PROC-11). Se extrajo a `summarize_outputs_by_type()`
(`use_cases/_shared.py`) para que `ReconcileYieldUseCase` no la duplicara —
`RecordProcessOutputsUseCase` se refactorizó para usar la misma función.

## Casos de uso (`backend/application/meat_processing/use_cases/yield_use_cases.py`)

| Use Case | Permiso | Comportamiento |
|---|---|---|
| `ReconcileYieldUseCase` | `YIELD_REVIEW` | Lee los `ProcessOutput` ya capturados de la orden (o de un lote específico), los suma con `summarize_outputs_by_type()`, construye y clasifica el `YieldReconciliation`. `expected_output_quantity`/`expected_output_weight` siempre los provee el llamador (mismo principio que PROC-11: nunca se asumen iguales a la entrada). |
| `ApproveYieldReconciliationUseCase` | `YIELD_APPROVE` | Llama al `YieldReconciliation.approve()` que existía sin uso desde PROC-2. Idempotente. |

## Alertas

`PROCESSING_YIELD_OUT_OF_TOLERANCE` (§60, ya existía desde PROC-2) es la
señal de alerta — se emite automáticamente cuando la clasificación es
`OUT_OF_TOLERANCE`/`CRITICAL`, tanto desde `RecordProcessOutputsUseCase`
(PROC-11) como ahora desde `ReconcileYieldUseCase`. No se creó una entidad
`Alert` — un consumidor real de notificaciones (PROC-20) se suscribe a este
evento cuando exista.

## Tests

`tests/integration/meat_processing/test_meat_processing_yield_use_cases.py::TestReconcileYield`/`TestApproveYieldReconciliation`
(6 tests: conciliación desde outputs ya capturados, falla sin outputs,
aprobación feliz + idempotencia, conciliación inexistente).

## Pendiente

- `YIELD_OVERRIDE` (§50, ya definido desde PROC-1) — para sobrescribir una
  clasificación automática con justificación manual; sin Use Case todavía.
- Vincular la aprobación del rendimiento como precondición del cierre de
  orden (§35 `OrderClosingPolicy.yield_calculated`/`variances_reviewed`, ya
  definida en PROC-2) — el `CloseProcessingOrderUseCase` real es fase futura.
