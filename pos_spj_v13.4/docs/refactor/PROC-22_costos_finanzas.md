# PROC-22 — Costos y Finanzas: Procesamiento Cárnico

Estado: **DONE** (`CloseProcessingOrderUseCase` — el capstone del ciclo de
vida de la orden, finalmente da uso real a `OrderClosingPolicy`/
`ProcessingOrderCloseChecklist`, construidos en PROC-2 y sin consumidor
hasta ahora)

## Alcance y decisión de arquitectura

§6/§46 son explícitos: "Costos administra... costo de transformación" —
Procesamiento nunca calcula ni postea un costo. La condición de eliminación
que PROC-0 fijó para el legacy `core/services/finance/production_cost_service.py`
es textual: "Procesamiento emite `PROCESSING_MATERIAL_CONSUMED`/
`PROCESSING_OUTPUT_PRODUCED`/`PROCESSING_ORDER_CLOSED` (ya definidos en
PROC-2 `events.py`) y el módulo de Costos los consume." Los dos primeros
eventos ya se emitían desde PROC-9/PROC-10; **`PROCESSING_ORDER_CLOSED` nunca
se había emitido**, porque nada llamaba `ProcessingOrder.close()` — ninguna
fase entre PROC-6 y PROC-21 construyó ese caso de uso, aunque
`OrderClosingPolicy`/`ProcessingOrderCloseChecklist` (PROC-2) ya modelaban
sus 9 precondiciones exactamente para este propósito, documentado en su
propio docstring: "the checklist is populated by the future
CloseProcessingOrder use case."

## `CloseProcessingOrderUseCase`

Vive en `processing_order_use_cases.py` (junto a Create/Approve/Release,
el resto del ciclo de vida de la orden). Exige `order.status == COMPLETED`
(`ORDER_NOT_COMPLETED` si no); idempotente si ya está `CLOSED`. Construye el
`ProcessingOrderCloseChecklist` **enteramente de datos que Procesamiento ya
tiene**, sin asumir que ninguna integración externa "seguro ya confirmó
algo":

| Precondición | Cómo se deriva |
|---|---|
| `consumptions_posted` | todo `MaterialConsumption` de la orden en `POSTED`/`REVERSED` |
| `outputs_registered` | al menos un `ProcessOutput` existe |
| `no_pending_weighings` | todo `ProcessWeighing` está `stable` o tiene `manual_override` autorizado |
| `quality_resolved` | ningún output sigue en `PENDING_INSPECTION` (una decisión se tomó, aunque sea bloqueante) |
| `yield_calculated` | existe al menos un `YieldReconciliation` |
| `variances_reviewed` | todos los `YieldReconciliation` de la orden están `APPROVED` |
| `critical_losses_have_case` | para cada reconciliación `OUT_OF_TOLERANCE`/`CRITICAL`, la bitácora tiene una entrada `LOSS_CASE_REQUESTED` (PROC-15) |
| `inventory_confirmed` | consumos `POSTED` e outputs no-`WASTE`/`LOSS` no-bloqueados por calidad tienen `inventory_operation_id` |
| `costs_notified` | `CostAllocationPort.request_cost_allocation(...)` devolvió una referencia, no `None` |

Si el checklist no está completo, `OrderClosingPolicy.ensure_can_close()`
levanta la excepción ya existente (PROC-2); el use case la traduce a
`CLOSE_PRECONDITIONS_NOT_MET` con `pending_items` en la respuesta — la UI
(o quien integre) sabe exactamente qué falta, no solo que algo falta.

## Puerto nuevo: `CostAllocationPort`

`request_cost_allocation(*, operation_id, processing_order_id, process_type)
-> str | None` — mismo patrón Port+Null que `LossCaseRequestPort`/
`QualityInspectionPort`/`NotificationPort` (PROC-15/16/20).
`NullCostAllocationPort` devuelve `None`; sin él, `costs_notified` queda
`False` y el cierre se rechaza honestamente en vez de fingir que Costos ya
confirmó. No se investigó una integración directa contra
`backend/domain/finance/` (contabilidad de partida doble, orientada a
asientos/cuentas, no a costeo unitario por orden) ni contra
`backend/domain/pricing/services/average_costing_service.py` (costeo
promedio de Inventario, otro concepto) — ninguno expone un puerto con esta
forma; construir uno real es integración futura, no parte de esta fase.

## Por qué no se reescribió `production_cost_service.py`

Se investigó reescribirlo contra el esquema nuevo (condición original de
eliminación en `PROC-0_legacy_audit.md`), pero sigue siendo el único
consumidor de las tablas legacy (`production_batches`,
`production_cost_ledger`) que `modulos/produccion.py` todavía usa — no se
toca hasta PROC-25. El nuevo `CostAllocationPort` no reemplaza esa lógica;
es el punto de entrada donde una futura implementación de Costos (ya sea una
adaptación de ese servicio o algo enteramente nuevo) se conectará al
bounded context nuevo.

## Tests

`tests/integration/meat_processing/test_meat_processing_order_closing_use_case.py`
(5 tests): orden no completada rechazada; cierre sin puerto de costeo falla
con `costs_notified` en `pending_items`; cierre exitoso con cada
precondición satisfecha (flujo completo: crear→aprobar→liberar→iniciar→
pesar→consumir+postear→producir+calidad+postear→conciliar+aprobar→
completar→cerrar) emite `PROCESSING_ORDER_CLOSED`; idempotencia; orden
desconocida falla.

## Pendiente

- `CostAllocationPort` real — integración futura, sin bounded context de
  Costos unitario todavía en el repo (ver arriba).
- El checklist no valida que `ProcessingOrder.production_area_id`/
  `.work_center_id` referencien un `WorkCenter` real del catálogo PROC-19 —
  fuera de alcance de esta fase (ver `PROC-19_recursos.md`, "Pendiente").
