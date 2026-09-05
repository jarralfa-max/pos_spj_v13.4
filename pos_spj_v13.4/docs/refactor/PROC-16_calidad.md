# PROC-16 — Calidad: Procesamiento Cárnico

Estado: **DONE** (solicitud de inspección + registro de decisión — sin
dominio nuevo en Procesamiento; Calidad es un módulo/bounded context externo
todavía por construir)

## Alcance y decisión de arquitectura

§28 es explícito: Procesamiento **nunca** decide si un output se libera,
se pone en cuarentena o se condena — eso es una decisión de Calidad.
`ProcessOutput.quality_status` (PROC-2) ya existía como un *setter* dócil
(`mark_quality_status`), nunca como una máquina de estados propia de
Procesamiento. PROC-16 construye el par de casos de uso que rodean ese
setter, siguiendo el mismo patrón Port+Null que PROC-6/9/10/15
(`RecipeSnapshotPort`/`InventoryConsumptionPort`/`InventoryReceiptPort`/
`LossCaseRequestPort`): `QualityInspectionPort.request_inspection(...)` con
default `NullQualityInspectionPort` que devuelve `None` en vez de fingir una
inspección solicitada.

## Casos de uso

- **`RequestQualityInspectionUseCase`** (`QUALITY_REQUEST_INSPECTION`): pide
  una inspección vía el puerto; sin puerto real responde
  `QUALITY_INTEGRATION_PENDING` (nunca inventa un `inspection_request_id`).
  Con puerto, además, si la orden está `IN_PROGRESS`/`PARTIALLY_COMPLETED`
  llama `order.request_quality_review()` (transición ya definida en
  `ProcessingOrder`, PROC-2/6); audita (`action="QUALITY_INSPECTION_REQUESTED"`)
  y emite `PROCESSING_QUALITY_REQUESTED`.
- **`RecordQualityDecisionUseCase`** (`QUALITY_RECORD_DECISION`): registra la
  decisión que Calidad ya tomó — Procesamiento solo la aplica
  (`output.mark_quality_status(decision)`). Idempotente si la decisión
  entrante coincide con el estado actual. Emite `PROCESSING_OUTPUT_RELEASED`
  si `decision == RELEASED`, o `PROCESSING_OUTPUT_BLOCKED` para cualquier
  estado bloqueante; el resultado incluye `blocked: bool` para que el
  caller no tenga que repetir la clasificación.

## Estados bloqueantes (compartidos)

`BLOCKED_QUALITY_STATUSES` (`QUARANTINED`, `REJECTED`, `CONDEMNED`,
`REWORK_REQUIRED`) se factorizó de una tupla local de
`output_use_cases.py` (`PostProcessOutputUseCase`,
`ChainOutputAsConsumptionUseCase`) a `use_cases/_shared.py`, para que
`quality_use_cases.py` no duplique la clasificación — un output bloqueado no
puede postearse a inventario ni encadenarse como consumo de otra orden, y
ahora tampoco puede reprocesarse fuera de ese conjunto (ver PROC-17).

## Nuevos permisos

`QUALITY_REQUEST_INSPECTION = "PRODUCCION.calidad.solicitar_inspeccion"`,
`QUALITY_RECORD_DECISION = "PRODUCCION.calidad.registrar_decision"` —
registrados en `core/security/permission_catalog.py` bajo `"PRODUCCION"`
(estándar Compras, no el patrón flat de Losses).

## Tests

`tests/integration/meat_processing/test_meat_processing_quality_use_cases.py`
(7 tests): sin puerto → pendiente; con puerto falso → éxito + auditado;
output desconocido → falla; decisión `RELEASED` emite evento de liberación;
decisión `CONDEMNED` emite evento de bloqueo; idempotencia en la misma
decisión; output desconocido falla también en el registro de decisión.

## Pendiente

- `QualityInspectionPort` real, cuando exista un módulo de Calidad
  (inspecciones, checklists, no-conformidades) — hoy solo el contrato y el
  `Null` existen.
- No hay todavía una entidad `QualityInspection`/`QualityHold` en
  Procesamiento ni se planea una: por diseño (§28), esa información vive del
  lado de Calidad; Procesamiento solo guarda el resultado final en
  `ProcessOutput.quality_status`.
