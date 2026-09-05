# PROC-15 — Mermas: Procesamiento Cárnico

Estado: **DONE** (variación, solicitud de expediente, idempotencia e
integración vía puerto — sin dominio nuevo en Procesamiento; Mermas/Losses ya
es un bounded context completo y externo a este)

## Alcance y decisión de arquitectura

§27 es explícito sobre el límite: "Mermas clasifica la pérdida... No duplicar
movimientos de inventario." Procesamiento **nunca** construye ni clasifica un
`LossCase` — eso ya vive, completo, en `backend/domain/losses/`
(`LossCase`, con `LossOrigin.PRODUCTION`/`.CUTTING`/`.SLAUGHTER_FUTURE` ya
anticipando recibir casos exactamente de este módulo, desde antes de que
Procesamiento existiera). Siguiendo el mismo patrón que
`RecipeSnapshotPort`/`InventoryConsumptionPort`/`InventoryReceiptPort`
(PROC-6/9/10), PROC-15 define `LossCaseRequestPort` — el contrato de lo que
Procesamiento necesita pedirle a Losses — con un default `Null` que dice
honestamente "integración pendiente" en vez de fingir un expediente creado.

## Variación

La variación ya la calcula `YieldReconciliation.status` (PROC-2, usado por
PROC-11/14): `OUT_OF_TOLERANCE`/`CRITICAL` es la señal de "existe una
variación que merece un expediente de merma" (§27). `RequestLossCaseForYieldVarianceUseCase`
rechaza (`WITHIN_TOLERANCE`) solicitar un expediente para una conciliación
que no está fuera de tolerancia — mermas no se abren especulativamente.

## Puerto nuevo: `LossCaseRequestPort`

`request_loss_case(*, operation_id, processing_order_id, product_id,
expected_weight, actual_weight, difference_weight, process_type,
processing_batch_id, lot_id, operator_ids, equipment_ids)` — exactamente los
campos que §27 pide que Procesamiento envíe. `operator_ids` se obtiene
reutilizando `OperatorAssignment` (PROC-7):
`uow.operator_assignments.list_active_by_order(order_id)` — ninguna
información nueva que rastrear, solo une dos piezas ya existentes.
`equipment_ids` queda vacío por ahora (no hay catálogo de equipos —
PROC-19); el parámetro existe en el puerto para cuando sí lo haya.

## Idempotencia

`RequestLossCaseForYieldVarianceUseCase` usa
`meat_processing_processed_events` (PROC-3) con el `operation_id` externo
como clave — mismo patrón que `RecordProcessOutputsUseCase` (PROC-11): un
reintento con el mismo `operation_id` no vuelve a llamar al puerto ni genera
un segundo expediente.

## Integración

`NullLossCaseRequestPort` (default) devuelve `None` → el Use Case responde
`LOSSES_INTEGRATION_PENDING`, nunca inventa un `loss_case_id`. Cuando se
solicita con éxito, el `loss_case_id` devuelto por el puerto se audita
(`meat_processing_audit_log`, `action="LOSS_CASE_REQUESTED"`) y se emite
`PROCESSING_LOSS_CASE_REQUESTED` (nuevo evento — §27 lo describe
textualmente como "`LOSS_CASE_REQUESTED`", aquí con el prefijo canónico
`PROCESSING_` del resto del catálogo).

## Nuevo permiso

`REQUEST_LOSS_CASE = "PRODUCCION.merma.solicitar"` — §50 no lista un permiso
específico para esta acción (las acciones de mermas viven del lado de
Losses); se añadió porque solicitar un expediente es, en sí, una acción del
lado de Procesamiento que debe poder auditarse y restringirse
independientemente de `YIELD_REVIEW`/`YIELD_APPROVE`.

## Tests

`tests/integration/meat_processing/test_meat_processing_yield_use_cases.py::TestRequestLossCaseForYieldVariance`
(5 tests: rechaza conciliación dentro de tolerancia, sin puerto → pendiente,
con puerto falso → éxito + `operator_ids` correctos + idempotencia,
conciliación inexistente).

## Pendiente

- `LossCaseRequestPort` real contra `RegisterGeneralLossUseCase` de Losses
  (`backend/application/losses/register_general_loss.py`) — cuando se
  decida el mecanismo de invocación cross-context (llamada directa de
  aplicación a aplicación, vs. a través de EventBus/outbox).
- `equipment_ids` — vacío hasta que exista un catálogo de equipos (PROC-19).
