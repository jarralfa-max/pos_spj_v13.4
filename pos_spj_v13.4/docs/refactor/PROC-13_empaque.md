# PROC-13 — Empaque: Procesamiento Cárnico

Estado: **DONE** (empaque, reempaque, lotes, caducidad y etiquetas con
reimpresión — dominio nuevo, primera fase desde PROC-9 que introduce
entidades genuinamente nuevas en vez de reutilizar lo existente)

## Alcance

§25: `PackagingExecution` y `ProductionLabel` — a diferencia de PROC-9/10/11/12
(que reutilizaron dominio de PROC-2), estas dos entidades no existían: ningún
otro flujo capturaba material de empaque, tara, fecha de caducidad,
código de barras o referencia QR.

## Dominio nuevo

- `PackagingExecution` (`entities/packaging_execution.py`) — registro
  inmutable (igual filosofía que `ProcessWeighing`: un hecho capturado, sin
  workflow de estados). Invariantes: `tare_weight <= gross_weight`,
  `net_weight <= gross_weight`, `expiration_date > production_date` cuando
  ambas están presentes. "Reempaque" no es un tipo distinto — es la misma
  entidad ejecutada bajo una orden de `ProcessType.REPACKAGING` (ya en el
  enum desde PROC-2); "Lotes" es el campo `lot_id` ya presente.
- `ProductionLabel` (`entities/production_label.py`) — `mark_printed()` fija
  `printed_at` la primera vez y solo incrementa `reprint_count` en llamadas
  posteriores (conserva la hora de la primera impresión). "La impresión no
  determina el éxito productivo" (§25) — la entidad de empaque nunca depende
  del estado de su etiqueta.

## Esquema

Migración **249** (`migrations/standalone/249_meat_processing_packaging_schema.py`,
tras la 248) añade `packaging_executions` y `production_labels`; 187 y 248
quedan intactos. `PackagingExecutionRepository`/`ProductionLabelRepository`
registrados en `MeatProcessingUnitOfWork` como
`uow.packaging_executions`/`uow.production_labels`.

**Corrección documental de paso:** los comentarios de la migración 248
(PROC-7/8) decían "migration 188" — un número hipotético usado antes de
confirmar cuál era el siguiente libre en el momento de escribirla; el número
real registrado siempre fue 248. Se corrigió el comentario para que coincida
con la realidad.

## Casos de uso (`backend/application/meat_processing/use_cases/packaging_use_cases.py`)

| Use Case | Permiso | Comportamiento |
|---|---|---|
| `ExecutePackagingUseCase` | `PACKAGING_EXECUTE` (§50, ya existía) | Crea el `PackagingExecution`; emite `PROCESSING_PACKAGING_EXECUTED` (nuevo, simétrico a los demás eventos de captura — pesaje, output, consumo — aunque §60 no lo nombraba explícitamente). |
| `PrintProductionLabelUseCase` | `LABEL_PRINT` | Crea la etiqueta y la marca impresa en el mismo paso; idempotente por `operation_id`. |
| `ReprintProductionLabelUseCase` | `LABEL_REPRINT` | Reimprime una etiqueta existente — permiso distinto del de la primera impresión, como pide §50. |

Ambos casos de impresión emiten `PROCESSING_LABEL_PRINTED` (§60, ya nombrado
ahí) con `reprint: bool` en el payload para distinguir primera impresión de
reimpresión sin necesitar dos eventos.

## Tests

`tests/unit/meat_processing/test_meat_processing_packaging_entities.py` (9
tests: cantidad positiva, tara/neto vs. bruto, caducidad, rechazo de float,
primera impresión vs. reimpresión), `tests/integration/meat_processing/test_meat_processing_packaging_use_cases.py`
(8 tests: ejecución de empaque + evento, orden inexistente, impresión +
idempotencia + empaque inexistente, reimpresión incrementa contador
preservando la hora original, reimpresión de etiqueta inexistente).

## Pendiente

- Vincular automáticamente `PackagingExecution.process_output_id` cuando el
  empaque parte de un `ProcessOutput` ya capturado (hoy es un campo opcional
  que el llamador debe pasar a mano).
- Plantillas de etiqueta reales (`label_template_id` es solo una referencia
  UUID; el motor de impresión/plantillas es infraestructura de hardware,
  fuera de alcance de este bounded context).
