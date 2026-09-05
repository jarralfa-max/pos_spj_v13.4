# PROC-11 — Despiece: Procesamiento Cárnico

Estado: **DONE** (esquemas de despiece consumidos vía snapshot, outputs
múltiples con huesos/grasa/recortes, cálculo de rendimiento — un único
mecanismo compartido con PROC-12, per §1)

## Alcance y decisión de diseño central

§1 (Principio Rector) es explícito: "No crear módulos paralelos
independientes para... Despiece... Todos deben compartir el mismo núcleo
productivo." Siguiendo eso literalmente, PROC-11 **no construye un mecanismo
propio** — implementa `RecordProcessOutputsUseCase`
(`use_cases/output_use_cases.py`, junto a los Use Cases de PROC-10) como la
orquestación de "una entrada conocida → varios outputs clasificados +
conciliación de rendimiento", que sirve tanto a despiece (PROC-11) como a
derivados (PROC-12) — la única diferencia entre ambos es el `ProcessType` de
la orden y cómo el llamador etiqueta cada línea de output, no el mecanismo.

## Mapeo de §23 a lo ya construido

| Elemento de §23 | Cómo se resuelve |
|---|---|
| Esquemas | `ProcessingOrder.cutting_scheme_version_id`, ya congelado en el snapshot de PROC-6 (`ReleaseProcessingOrderUseCase` + `RecipeSnapshotPort`) — Procesamiento consume la versión activa, nunca la modifica (§14). |
| Multiespecie | Sin código específico por especie en Procesamiento — la especie es un atributo del `product_id`/receta que resuelve Productos (§2/§6: "Productos define qué puede producirse"). `ProcessType` ya es genérico (`CUTTING`, `DISASSEMBLY`, `DEBONING`, `TRIMMING` sirven para cualquier especie). |
| Outputs múltiples | `RecordProcessOutputsUseCase` acepta una lista arbitraria de líneas de output en una sola transacción. |
| Huesos / Grasa / Recortes | No son tipos de output nuevos — son líneas `CO_PRODUCT`/`BY_PRODUCT`/`WASTE` con un `product_id` descriptivo (huesos, grasa, recorte son productos del catálogo de Productos). Modelarlos como tipos de `OutputType` separados habría sido la duplicación que PROC-2 ya evitó explícitamente. |

## Rendimiento en la misma transacción

`RecordProcessOutputsUseCase` acumula `actual_output_quantity/weight` (solo
`MAIN_PRODUCT`), `co_product_weight`, `by_product_weight` y `waste_weight` a
partir de las líneas capturadas, construye una `YieldReconciliation` (PROC-2)
y la clasifica con `YieldReconciliationPolicy.classify()` (PROC-2) —
`warning_pct`/`tolerance_pct`/`critical_pct` siempre los provee el llamador,
nunca hardcodeados (§26). Si el resultado es `OUT_OF_TOLERANCE`/`CRITICAL`,
emite además `PROCESSING_YIELD_OUT_OF_TOLERANCE`.

**Corrección de diseño detectada al escribir los tests:** la primera versión
asumía `expected_output_weight = input_weight`, lo cual es conceptualmente
incorrecto — el output esperado normalmente es *menor* que la entrada (esa
proporción **es** el rendimiento esperado). Se corrigió: `RecordProcessOutputsUseCase`
ahora exige `expected_output_quantity`/`expected_output_weight` como
parámetros propios y explícitos, nunca derivados de `input_weight`.

## Idempotencia

Como la llamada abarca varias entidades (cada línea de output +
la reconciliación), cada una necesita su propio `operation_id` UUIDv7 válido
— no se pueden derivar por sufijo del `operation_id` externo (eso rompía la
validación UUIDv7). La idempotencia de toda la llamada se rastrea aparte, vía
`meat_processing_processed_events` (ya existente desde PROC-3): un reintento
con el mismo `operation_id` externo devuelve éxito idempotente sin duplicar
outputs ni la reconciliación.

## Tests

`tests/integration/meat_processing/test_meat_processing_output_use_cases.py::TestRecordProcessOutputs`
(dentro de tolerancia con 4 líneas, idempotencia sin duplicar outputs,
fuera de tolerancia emite alerta, rechaza lista vacía).

## Pendiente

- `MaterialAvailabilityPort`/reservas reales contra el `cutting_scheme_version_id`
  congelado (hoy el snapshot solo se referencia, no se valida su contenido
  contra los outputs capturados).
- Decomisos y clasificación de canales — fuera de alcance hasta Sacrificio
  futuro (PROC-24).
