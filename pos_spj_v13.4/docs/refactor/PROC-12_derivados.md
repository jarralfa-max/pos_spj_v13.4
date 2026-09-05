# PROC-12 — Productos derivados: Procesamiento Cárnico

Estado: **DONE** (molido/mezclado/marinado/formulación resueltos por el mismo
mecanismo que PROC-11; BOM multinivel resuelto encadenando output→consumo
entre órdenes)

## Alcance y reutilización de PROC-11

Igual razonamiento que en `PROC-11_despiece.md`: §1 prohíbe un mecanismo
paralelo, así que "derivados" usa exactamente `RecordProcessOutputsUseCase`
(`use_cases/output_use_cases.py`). Lo único distinto es semántico: el
`ProcessType` de la orden (`GRINDING`, `MIXING`, `MARINATION`, `FORMULATION`
— los cuatro ya existían en el enum desde PROC-2) y qué representan las
líneas de output (un embutido, una mezcla marinada, una formulación) en vez
de cortes/huesos/grasa.

## Mapeo de §24 a lo ya construido

| Elemento de §24 | Cómo se resuelve |
|---|---|
| Molido / Mezclado / Marinado / Formulación | `ProcessType.GRINDING`/`.MIXING`/`.MARINATION`/`.FORMULATION` (ya en el enum, PROC-2) + `RecordProcessOutputsUseCase` (PROC-11) para capturar los outputs y su rendimiento. Sin código nuevo específico por tipo de proceso — el núcleo no distingue. |
| Porcionado | `ProcessType.PORTIONING`, mismo mecanismo. |
| Embutidos / cocción / ahumado / curado futuros | `ProcessType.SAUSAGE_PRODUCTION_FUTURE`/`.COOKING_FUTURE`/`.SMOKING_FUTURE`/`.CURING_FUTURE` ya están en el enum (PROC-2) como valores reservados — sin implementación específica todavía, consistente con "futuro". |
| BOM multinivel / productos intermedios | `ChainOutputAsConsumptionUseCase` (nuevo, ver abajo). |

## BOM multinivel — `ChainOutputAsConsumptionUseCase`

El mecanismo concreto: el `ProcessOutput` de una orden "aguas arriba" (p. ej.
una `SEMI_FINISHED` de una orden de molido) se convierte en el
`MaterialConsumption` de una orden "aguas abajo" (p. ej. una orden de
mezclado que lo usa como insumo) — mismo `product_id`, `lot_id`, cantidad y
peso, registrado y con sus reales ya capturados
(`consumption.record_actuals()`, PROC-2) en una sola llamada. No se creó
ninguna entidad "BOM" nueva: el encadenamiento *es* la relación entre dos
entidades que ya existían (`ProcessOutput` → `MaterialConsumption`), lo que
demuestra que "multinivel" no necesitaba modelado adicional — cualquier
profundidad de niveles se logra encadenando esta llamada tantas veces como
haga falta.

La cadena respeta la misma regla de calidad que `PostProcessOutputUseCase`
(PROC-10): un output de origen bloqueado (`QUARANTINED`/`REJECTED`/
`CONDEMNED`/`REWORK_REQUIRED`) no puede encadenarse
(`OUTPUT_QUALITY_BLOCKED`).

## Tests

`tests/integration/meat_processing/test_meat_processing_output_use_cases.py::TestChainOutputAsConsumption`
(encadena un output `SEMI_FINISHED` como consumo de una orden `MIXING`;
rechaza encadenar un output bloqueado por calidad).

## Pendiente

- El `MaterialConsumption` resultante del encadenamiento queda en
  `PENDING_POSTING` — todavía requiere `PostMaterialConsumptionUseCase`
  (PROC-9) y su propio `InventoryConsumptionPort` para postear de verdad.
- Trazabilidad de la cadena completa (genealogía multinivel consultable) —
  PROC-18.
