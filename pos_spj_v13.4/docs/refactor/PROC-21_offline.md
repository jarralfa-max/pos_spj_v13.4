# PROC-21 — Offline: Procesamiento Cárnico

Estado: **DONE** (registro en el motor de sync multi-sucursal + validador de
dominio nuevo para el esquema born-clean; sin tocar `ProductionValidator`
legacy)

## Alcance y decisión de arquitectura

`sync/sync_engine.py` (outbox local + Lamport clock) y
`sync/conflict_resolver.py` (LWW/ADDITIVE/SERVER_AUTH por tabla) son
infraestructura compartida por **todo** el POS, no algo que Procesamiento
reimplementa — "secuencia" (Lamport) y "outbox" (cola persistente) ya
funcionan de forma genérica para cualquier tabla que esté en
`TABLAS_SINCRONIZABLES`. Antes de esta fase, esa lista solo tenía las tablas
legacy (`production_batches`, `production_batch_outputs`) — ninguna de las
casi veinte tablas del bounded context nuevo (PROC-2 en adelante) se
sincronizaba entre sucursales. El trabajo real de PROC-21 es (a) inscribir
las tablas correctas, (b) clasificarlas correctamente en la política de
resolución de conflictos, y (c) el validador de dominio que la auditoría
PROC-0 marcó como pendiente de reescritura.

`docs/refactor/PROC-0_legacy_audit.md` clasificó
`sync/domain_validators/production_validator.py` como `REWRITE`. La
auditoría original asumía reescribir ese archivo; en la práctica,
`tests/test_refactor_v133.py::TestProductionValidator` fija su
comportamiento contra las tablas legacy (`production_batches`,
`estado`/`folio` en español, `float`) que **siguen existiendo** — la UI
legacy (`modulos/produccion.py`) no se ha migrado ni eliminado (eso es
PROC-25). Reescribir ese archivo habría roto esos tests sin necesidad.
Se optó por **añadir** un validador hermano (`MeatProcessingValidator`) para
el esquema nuevo, dejando `ProductionValidator` intacto hasta que PROC-25
elimine las tablas legacy que valida.

## Tablas registradas para sync (`TABLAS_SINCRONIZABLES`)

Las ~20 tablas del bounded context, con dos exclusiones deliberadas:
`meat_processing_outbox` y `meat_processing_processed_events` son
mecanismos **locales por nodo** (publicación de eventos de dominio /
idempotencia de este dispositivo específico) — sincronizarlas entre
sucursales las corrompería, cada nodo necesita su propia copia
independiente. El resto (`processing_orders` hasta
`meat_processing_authorization_log`) sí se registra: incluye la auditoría
(`meat_processing_audit_log`/`_authorization_log`) porque en un ERP
multi-sucursal esa evidencia debe ser visible centralmente, no solo local.

## Clasificación de conflictos (`SERVER_AUTH_TABLES`)

`processing_orders`, `processing_batches`, `process_executions`,
`material_consumptions`, `process_outputs`, `process_weighings`,
`yield_reconciliations`, `rework_orders` — los agregados con máquina de
estados auditable, mismo trato que `ventas`/`ordenes_compra`: ante un
conflicto, el servidor gana en vez de fusionar por última escritura, para no
divergir en silencio sobre un estado que ya tiene consecuencias financieras/
operativas aguas abajo. El resto de las tablas del bounded context
(`material_requirements`, `operator_assignments`, `process_incidents`,
`packaging_executions`, `production_labels`, `process_genealogy_links`,
catálogo de recursos, auditoría) se deja en el LWW por defecto — mismo
criterio que separa `compras` (SERVER_AUTH) de `detalles_compra` (LWW).

## Validador nuevo: `MeatProcessingValidator`

`sync/domain_validators/meat_processing_validator.py`, registrado en
`get_default_validators()` junto a `ProductionValidator` (aditivo, no lo
reemplaza). Reglas, Decimal-safe (nunca `float`), sobre nombres de columna
en inglés del esquema nuevo:

1. `processing_orders`: una orden `CLOSED` localmente nunca se reabre por un
   estado remoto anterior en el ciclo de vida (§13) — red de seguridad para
   cuando el escritor remoto nunca vio ese cierre.
2. `yield_reconciliations`: variación `input_weight` vs.
   `actual_output_weight` mayor a `max_variance_pct` (parámetro del
   constructor, default 50 — nunca hardcodeado dentro del método) se marca
   sospechosa. Réplica Decimal-safe de la regla de "merma extrema" del
   validador legacy, sobre los nombres de columna correctos del esquema
   nuevo.
3. `process_outputs`: un output ya posteado a inventario
   (`inventory_operation_id` presente) con `weight` y `quantity` en cero es
   un estado que la propia `CHECK` de la tabla nunca dejaría insertar de
   forma nativa — si llega así por sync, el dato ya viene corrupto de
   origen.

No se replicó la regla de "cost ratio" del validador legacy (rechazar
asignación de costo > 200% de la materia prima) — el costeo de Procesamiento
es explícitamente responsabilidad de Costos/Finanzas (§6/§46, PROC-22), no
de este bounded context; replicarla aquí habría sido validar una tabla que
Procesamiento ni siquiera posee.

## Tests

`tests/unit/meat_processing/test_meat_processing_sync_validator.py`
(10 tests): tabla ajena ignorada; reapertura de orden cerrada rechazada,
cerrada→cerrada aceptada, progresión normal aceptada; variación dentro de
umbral aceptada, variación extrema rechazada, `input_weight=0` no produce
división por cero; output posteado con peso/cantidad cero rechazado, output
posteado con peso positivo aceptado, output no posteado con cero aceptado
(no es sospechoso si aún no se finalizó).
`tests/test_refactor_v133.py::TestProductionValidator` (4 tests, ya
existentes) reejecutados sin cambios — confirman que el validador legacy
sigue intacto.

## Pendiente

- El validador legacy `ProductionValidator` y sus tablas
  (`production_batches`/`production_outputs`/`production_cost_ledger`)
  siguen vivos hasta PROC-25 (eliminación de legacy) — en ese momento,
  eliminar también su registro en `get_default_validators()` y sus tests en
  `tests/test_refactor_v133.py`.
- Sin pruebas de integración de extremo a extremo contra `SyncEngine`/
  `ConflictResolver` reales (solo el validador de dominio en aislamiento,
  igual que el precedente legacy) — el motor de sync en sí no tiene un test
  harness de multi-nodo en este repo todavía.
