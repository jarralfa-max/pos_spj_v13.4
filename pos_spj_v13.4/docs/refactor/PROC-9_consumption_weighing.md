# PROC-9 — Consumos y pesajes: Procesamiento Cárnico

Estado: **DONE** (captura de pesaje con autorización de override, captura y
posteo de consumo vía puerto de Inventario — sin dominio nuevo, `MaterialConsumption`
y `ProcessWeighing` ya existían completos desde PROC-2/PROC-3)

## Alcance

A diferencia de PROC-7/8, esta fase no crea entidades ni tablas nuevas —
`MaterialConsumption` y `ProcessWeighing` (con sus invariantes de peso estable
y autorización de override) ya estaban completos desde PROC-2, y su
persistencia desde PROC-3. PROC-9 es la primera vez que esa infraestructura
se **usa** desde un Use Case real, y la primera vez que
`meat_processing_authorization_log`/`AuthorizationGrant` (construidos en
PROC-1/PROC-3, sin consumidor hasta ahora) se escriben de verdad.

## Peso estable / Manual override (§21)

La regla estructural ("no se acepta un peso inestable sin captura manual
autorizada"; "un override manual requiere `authorized_by_user_id`") ya vivía
en `ProcessWeighing.__post_init__`. Lo que faltaba era la mitad de
**autorización**: que el `authorized_by_user_id` realmente *tenga permiso*
para autorizar. `CaptureProcessWeighingUseCase` añade ese chequeo — si
`manual_override=True`, exige `WEIGHT_MANUAL_OVERRIDE` sobre
`authorized_by_user_id` (no sobre el capturador) antes de construir la
entidad, y registra un `AuthorizationGrant` en
`meat_processing_authorization_log` con el peso neto capturado. Esta es la
primera autorización en caliente real del bounded context (§52).

## Consumos e Inventario (§17/§39)

`CaptureMaterialConsumptionUseCase` crea el `MaterialConsumption` y registra
sus reales en una sola llamada (el flujo común: se pesa, se captura la
cantidad real). Si se provee `tolerance_pct`, se valida con
`ConsumptionPolicy.validate_overage()` (PROC-2); si excede, exige
`CONSUMPTION_OVERRIDE` sobre un `authorized_by_user_id` y registra el
`AuthorizationGrant` correspondiente — mismo patrón que el override de peso.

`PostMaterialConsumptionUseCase` es donde se respeta literalmente §39
("Procesamiento nunca escribe movimientos de inventario"): llama a
`InventoryConsumptionPort.post_consumption(...)` y **solo** marca el consumo
`POSTED` si el puerto devuelve un `inventory_operation_id` real.
`NullInventoryConsumptionPort` (el default) devuelve `None` — el Use Case
responde `INVENTORY_INTEGRATION_PENDING`, nunca finge una integración que no
existe. Esto es deliberadamente distinto del patrón `NullRecipeSnapshotPort`
de PROC-6 (que sí deja avanzar la orden sin snapshot, porque un proceso sin
receta es legítimo): aquí un consumo *siempre* necesita que Inventario
confirme, así que "sin integración" debe ser un fallo explícito, no un
"éxito" silencioso.

## Puerto nuevo

`InventoryConsumptionPort` (`backend/application/meat_processing/ports.py`) +
`NullInventoryConsumptionPort` — mismo patrón `Protocol` + default no-op que
`RecipeSnapshotPort` (PROC-6).

## Casos de uso (`backend/application/meat_processing/use_cases/consumption_weighing_use_cases.py`)

| Use Case | Permiso | Comportamiento |
|---|---|---|
| `CaptureProcessWeighingUseCase` | `WEIGHT_CAPTURE` (+ `WEIGHT_MANUAL_OVERRIDE` sobre el autorizador si `manual_override`) | Crea el pesaje; audita el override si aplica; emite `PROCESSING_WEIGHT_CAPTURED`. |
| `CaptureMaterialConsumptionUseCase` | `CONSUMPTION_CAPTURE` (+ `CONSUMPTION_OVERRIDE` sobre el autorizador si excede tolerancia) | Crea el consumo con sus reales ya registrados (`DRAFT → PENDING_POSTING`). |
| `PostMaterialConsumptionUseCase` | `CONSUMPTION_CAPTURE` | Solicita el movimiento a `InventoryConsumptionPort`; solo postea (`→ POSTED`) si hay `inventory_operation_id`; idempotente si ya estaba `POSTED`. |

## Tests

`tests/integration/meat_processing/test_meat_processing_consumption_weighing_use_cases.py`
(10 tests: pesaje estable, override sin permiso denegado — con un checker que
otorga `WEIGHT_CAPTURE` pero no `WEIGHT_MANUAL_OVERRIDE`, para no depender del
checker permisivo por defecto —, override autorizado con `AuthorizationGrant`
verificado en la tabla, peso inestable sin override rechazado por el dominio,
consumo dentro de tolerancia, consumo excedido sin autorizador rechazado,
consumo excedido con autorizador aceptado, posteo sin puerto → pendiente,
posteo con puerto falso → `POSTED` + idempotente, posteo de consumo
inexistente).

## Pendiente

- `InventoryConsumptionPort` real contra `PostProductionConsumptionUseCase`
  de Inventario (§39) — cuando ese punto de integración exista.
- Vincular `MaterialConsumption.weighing_id` automáticamente cuando un
  pesaje y un consumo se capturan en el mismo flujo operativo (hoy ambos Use
  Cases son independientes; el llamador debe pasar `weighing_id` a mano).
- Reversión de consumo posteado (`MaterialConsumption.reverse()` ya existe en
  el dominio desde PROC-2, sin Use Case todavía) — natural candidato para
  PROC-25/cierre o para una fase de correcciones.
