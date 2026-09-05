# PROC-17 — Reprocesos: Procesamiento Cárnico

Estado: **DONE** (crear → aprobar → ejecutar → completar → cerrar, sin motor
de ejecución paralelo)

## Alcance y decisión de arquitectura

§1 (Principio Rector) prohíbe mecanismos paralelos por tipo de proceso: un
reproceso no es un tipo de orden distinto, es una `ProcessingOrder` normal
que corre por el mismo núcleo productivo (creación → aprobación →
liberación → ejecución → outputs → cierre, PROC-6..12), solo que su
`source_type="REWORK_ORDER"` y `source_reference_id=rework.id` documentan de
dónde salió. `StartReworkExecutionUseCase` crea una orden **nueva** — la
orden origen y su output bloqueado nunca se tocan; "no modificar
silenciosamente la orden original" (§29) queda garantizado por construcción,
no por una validación aparte.

## Entidad nueva: `ReworkOrder`

`backend/domain/meat_processing/entities/rework_order.py`. Campos:
`source_output_id`, `product_id`, `origin: ReworkOrigin`,
`created_by_user_id`, `quantity`/`weight` (con default = los del output
origen si no se especifican), `reason`, `status: ReworkOrderStatus`,
`approved_by_user_id`, `processing_order_id` (se llena al ejecutar).

`ReworkOrigin`: `QUALITY_DECISION`, `PROCESSING_INCIDENT`,
`OUTPUT_VARIANCE`, `PACKAGING_FAILURE`, `CUSTOMER_RETURN_AUTHORIZED`.

`ReworkOrderStatus`: `CREATED → APPROVED → IN_PROGRESS → COMPLETED → CLOSED`,
con `CANCELLED` alcanzable desde `CREATED`/`APPROVED`.

Segregación de funciones (§51): `approve()` rechaza si
`approved_by_user_id == created_by_user_id`, levantando
`MeatProcessingSegregationOfDutiesError` — mismo patrón que
`ProcessingOrder.approve()` (PROC-6).

## Casos de uso

- **`CreateReworkOrderUseCase`** (`REWORK_CREATE`): exige que el output
  origen esté en `BLOCKED_QUALITY_STATUSES` (compartido con PROC-16) —
  `OUTPUT_NOT_BLOCKED` si no lo está; un reproceso nunca se abre
  especulativamente sobre un output sano.
- **`ApproveReworkOrderUseCase`** (`REWORK_APPROVE`, idempotente).
- **`StartReworkExecutionUseCase`** (`REWORK_EXECUTE`): crea la
  `ProcessingOrder` nueva descrita arriba y transiciona el reproceso a
  `IN_PROGRESS`; idempotente (reintento devuelve la misma
  `processing_order_id`).
- **`CompleteReworkOrderUseCase`** (`REWORK_EXECUTE`, idempotente): carga la
  `ProcessingOrder` creada por `StartReworkExecutionUseCase` **dentro de la
  misma UoW** para tomar su `branch_id`/`warehouse_id` al construir el
  evento — el reproceso en sí no guarda esos campos (viven en la orden que
  ejecuta el trabajo). Emite `PROCESSING_REWORK_COMPLETED`.
- **`CloseReworkOrderUseCase`** (`REWORK_CLOSE`, idempotente).

## Permisos

`REWORK_VIEW`/`CREATE`/`APPROVE`/`EXECUTE`/`CLOSE` ya existían desde PROC-1
(`PRODUCCION.reproceso.*`); PROC-17 es su primer uso real.

## Tests

`tests/integration/meat_processing/test_meat_processing_rework_use_cases.py`
(15 tests): creación desde output bloqueado / rechazo si no está bloqueado /
output desconocido; aprobación + idempotencia + no-encontrado; ejecución crea
una orden nueva sin tocar la orden origen + idempotencia + no-encontrado;
completado emite evento + idempotencia + no-encontrado; cierre +
idempotencia + no-encontrado.

## Pendiente

- No hay todavía UI para el flujo de reprocesos (fuera de alcance de esta
  fase, como el resto del backend PROC-*).
- El reproceso no genera automáticamente un `ProcessGenealogyLink` hacia la
  nueva orden que ejecuta el trabajo — el output bloqueado origen y la orden
  de reproceso quedan relacionados solo por `ReworkOrder.source_output_id`/
  `.processing_order_id`, no por el grafo de PROC-18 (que solo modela
  cadenas output→consumo). Si en el futuro se necesita trazar reprocesos
  desde `ProcessGenealogyQueryService`, hay que decidir cómo modelarlo (¿un
  tipo de entidad nuevo en el grafo, o basta con la FK existente?).
