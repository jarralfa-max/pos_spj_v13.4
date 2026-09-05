# PROC-10 — Outputs: Procesamiento Cárnico

Estado: **DONE** (captura de producto principal/coproductos/subproductos/WIP
+ posteo a Inventario; sin dominio nuevo — `ProcessOutput` ya existía completo
desde PROC-2)

## Alcance

Igual que PROC-9, esta fase no crea entidades ni tablas: `ProcessOutput`
(discriminado por `OutputType`, ver nota de diseño en PROC-2) ya cubre
producto principal, coproductos, subproductos, WIP y merma con la misma
forma de campos. PROC-10 es la primera vez que se captura y postea de verdad.

## Casos de uso (`backend/application/meat_processing/use_cases/output_use_cases.py`)

| Use Case | Comportamiento |
|---|---|
| `CaptureProcessOutputUseCase` | Crea un `ProcessOutput`. El permiso se resuelve por `output_type` (`_PERMISSION_BY_OUTPUT_TYPE`): `MAIN_PRODUCT→OUTPUT_CAPTURE`, `CO_PRODUCT→CO_PRODUCT_CAPTURE`, `BY_PRODUCT→BY_PRODUCT_CAPTURE`, `SEMI_FINISHED`/`WORK_IN_PROGRESS`/`REWORKABLE→SUBPRODUCT_CAPTURE`, `WASTE`/`LOSS→WASTE_CAPTURE` — los 6 permisos de §50 ya existían desde PROC-1, sin necesidad de ampliar el catálogo. Emite el evento correspondiente (`_EVENT_BY_OUTPUT_TYPE`, los 5 eventos de outputs de §60 ya existían desde PROC-2). |
| `PostProcessOutputUseCase` | §39: pide a `InventoryReceiptPort` que reciba el output; solo marca `inventory_operation_id` si el puerto confirma. Bloquea (`OUTPUT_QUALITY_BLOCKED`) si `quality_status` es `QUARANTINED`/`REJECTED`/`CONDEMNED`/`REWORK_REQUIRED` — `PENDING_INSPECTION` (el default) **sí** puede postear, porque Calidad como módulo real todavía no existe (PROC-16); solo los estados explícitamente negativos bloquean, no la ausencia de decisión. Idempotente si `inventory_operation_id` ya está asignado. |

## Puerto nuevo

`InventoryReceiptPort` + `NullInventoryReceiptPort` (`ports.py`) — mismo
patrón que `InventoryConsumptionPort` de PROC-9.

## Tests

`tests/integration/meat_processing/test_meat_processing_output_use_cases.py`
(clase `TestCaptureProcessOutput`/`TestPostProcessOutput`; ver también
PROC-11/12 en el mismo archivo, que comparte fixtures).

## Pendiente

- `InventoryReceiptPort` real — cuando Inventario exponga el punto de
  integración de recepción de producción.
- La regla "PENDING_INSPECTION sí postea" es una decisión interina explícita
  hasta que PROC-16 (Calidad) exista; revisar si debe endurecerse una vez ese
  módulo pueda emitir una decisión real antes de postear.
