# PROC-3 — Esquema limpio: Procesamiento Cárnico

Estado: **DONE** (esquema + repositorios + UoW; sin Use Cases ni UI todavía)

## Alcance

UUIDv7, Decimal, constraints, índices, outbox y bootstrap para el núcleo
productivo definido en PROC-2 (`ProcessingOrder`, `ProcessingBatch`,
`ProcessExecution`, `MaterialConsumption`, `ProcessOutput`, `ProcessWeighing`,
`YieldReconciliation`), siguiendo el patrón de Inventario/Customers-CRM:
`backend/infrastructure/db/schema/meat_processing_schema.py` (DDL) +
migración delgada que solo lo invoca +
`backend/infrastructure/db/repositories/meat_processing/` (un repositorio por
entidad + soporte) + `MeatProcessingUnitOfWork` (un límite transaccional).

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `backend/infrastructure/db/schema/meat_processing_schema.py` | `MEAT_PROCESSING_TABLES`, `_DDL`, `_INDEXES`, `create_meat_processing_schema(conn)`, `drop_meat_processing_schema(conn)`. 12 tablas: las 7 del núcleo + `processing_batch_source_lots` (relación many-to-many lote↔lotes origen) + `meat_processing_{authorization_log,audit_log,outbox,processed_events}`. |
| `migrations/standalone/187_meat_processing_bounded_context_schema.py` | Migración delgada (`run(conn)` → `create_meat_processing_schema(conn)` → `commit()`), registrada en `migrations/engine.py` tras la 186. |
| `backend/infrastructure/db/repositories/meat_processing/base.py` | `MeatProcessingRepositoryBase` (`_query`/`_query_one`/`_execute`/`_scalar`) + helpers `dec_str`/`opt_dec_str`/`to_decimal`/`opt_decimal`/`dt_str`/`parse_dt`/`enum_value`/`bool_int`/`int_bool`/`now_iso`. |
| `.../{processing_order,processing_batch,process_execution,material_consumption,process_output,process_weighing,yield_reconciliation}_repository.py` | Un repositorio por entidad: `save()` (upsert `ON CONFLICT(id) DO UPDATE`, salvo `ProcessWeighing` que es solo-inserción — es una captura inmutable), `get()`, `list_by_order()`/`list_by_batch()`. Cada uno reconstruye la entidad de dominio completa desde la fila (round-trip real, no solo DTOs). |
| `.../support_repositories.py` | `MeatProcessingAuthorizationLogRepository`, `MeatProcessingAuditRepository`, `MeatProcessingOutboxRepository`, `MeatProcessingProcessedEventRepository` — mirror de las de Inventario. |
| `.../unit_of_work.py` | `MeatProcessingUnitOfWork` — agrega los 11 repositorios; `owns_transaction=False` para flujos donde un caso de uso externo (p. ej. Inventario) es dueño de la transacción. |

## Decisión de diseño: reconstrucción de agregados (corrección a PROC-2)

Al construir los repositorios se detectó un conflicto real: los `__post_init__`
de `ProcessingOrder`, `ProcessingBatch`, `ProcessExecution`,
`MaterialConsumption` y `YieldReconciliation` (PROC-2) exigían que toda
instancia nueva iniciara en un estado "fresco" (`DRAFT`/`PLANNED`/
`NOT_STARTED`/`PENDING_REVIEW`). Eso es incompatible con `repository.get()`,
que debe poder reconstruir una orden ya `CLOSED` o un lote ya `COMPLETED`
directamente desde la fila de la base de datos.

Se investigaron los dos precedentes ya existentes en el repo:
- **Inventario** (`InventoryAdjustment`, etc.): sin ese guard — las entidades
  se reconstruyen libremente en cualquier estado; `AdjustmentRepository.get()`
  hace exactamente eso.
- **Losses** (`LossCase`): sí tiene el guard — pero, al revisarlo, su
  repositorio **nunca reconstruye** un `LossCase` completo desde storage; solo
  construye instancias frescas dentro de un único Use Case (`LossCase(...)`
  siempre con `status` por default). Losses nunca necesitó resolver este
  problema porque nunca hace `get()` → mutar → `save()`.

Como Procesamiento Cárnico sí necesita ese ciclo completo (PROC-6+: cargar una
orden existente, aprobarla, liberarla, cerrarla), se adoptó el patrón de
Inventario: se eliminaron los 5 guards "debe iniciar en X" de PROC-2. El
`status` por default de cada dataclass (p. ej.
`status: ProcessingOrderStatus = ProcessingOrderStatus.DRAFT`) sigue
garantizando que un Use Case de creación que no pase `status=` explícito
obtenga el estado inicial correcto — la protección contra un estado inicial
incorrecto se mueve de "invariante del constructor" a "responsabilidad del
Use Case de creación", que es donde ya vivía en la práctica (ningún Use Case
de creación pasaría `status=CLOSED` a una entidad nueva).

## Otra corrección detectada durante PROC-3

`ProcessExecution.total_paused_seconds` estaba tipado `float` en PROC-2 — una
violación Decimal-only que solo se hizo evidente al diseñar la columna de
persistencia. Se corrigió a `Decimal` (igual que `duration_seconds`, la
propiedad calculada). Ver `backend/domain/meat_processing/entities/process_execution.py`.

## Serialización de fechas (dominio `datetime` vs. columna `TEXT`)

Las entidades mantienen `datetime` real (no `str`) para poder operar
aritmética de duración (`ProcessExecution.pause()/resume()`). Python 3.12+ ya
no registra adaptadores `datetime` por defecto en `sqlite3`, así que la
conversión ocurre explícitamente en el límite del repositorio: `dt_str()`
(`datetime → isoformat str`) al guardar, `parse_dt()`
(`str → datetime.fromisoformat`) al reconstruir. El dominio permanece puro;
solo la infraestructura conoce la representación TEXT.

## Auditoría REGLA CERO

| Regla | Verificación |
|---|---|
| UUIDv7 único, sin enteros | Todo `id` es `TEXT PRIMARY KEY`; `operation_id` es `UNIQUE CHECK(operation_id <> id)` en las 7 tablas núcleo. Sin `AUTOINCREMENT`, sin `lastrowid` — confirmado por `tests/architecture/test_meat_processing_repositories_never_commit.py` (los repositorios no definen DDL) y por inspección manual. |
| Decimal-only | Toda columna cantidad/peso/porcentaje es `TEXT` con `CHECK(CAST(x AS NUMERIC) >= 0)`; `dec_str()`/`opt_dec_str()` en el repositorio rechazan `float` explícitamente (`raise ValueError`), igual que su equivalente en Inventario. |
| Sin drift esquema↔dominio | Los `CHECK (col IN (...))` de `process_type`/`status`/`output_type`/etc. se generan con `_values(enum_type)` importando directamente `backend.domain.meat_processing.enums` — no hay listas de valores escritas a mano por duplicado. |
| Repositorios nunca hacen commit/rollback | Solo `MeatProcessingUnitOfWork` toca `connection.commit()`/`rollback()`; verificado por `test_meat_processing_repositories_never_commit.py`. |
| Solo `migrations/` modifica schema | `CREATE TABLE`/`ALTER TABLE` existen únicamente en `meat_processing_schema.py`; los repositorios no contienen DDL (mismo test). |
| Sin legacy tocado | `producciones`/`produccion_detalle` no aparecen en `MEAT_PROCESSING_TABLES` ni se leen/escriben desde los nuevos repositorios (verificado en `test_meat_processing_schema_born_clean.py::test_no_legacy_production_table_names_are_touched`). |

## Tests

- `tests/integration/meat_processing/test_meat_processing_schema_born_clean.py` —
  tablas completas, PKs TEXT, idempotencia, `operation_id` único y distinto de
  `id`, `CHECK` de status/tipo canónico, cantidad/peso no-negativo, no-ambos-cero
  en `processing_orders`, FK internas (huérfanos rechazados), invariante de
  `process_weighings.manual_override`, idempotencia de outbox/processed_events.
- `tests/integration/meat_processing/test_meat_processing_repositories.py` —
  round-trip completo (`save` → `get` → igualdad de entidad) de las 7 entidades
  núcleo + `processing_batch_source_lots`, upsert de transición de estado,
  comportamiento de `MeatProcessingUnitOfWork` (`commit`/`rollback`/
  `owns_transaction=False`), repositorios de soporte (outbox, processed events,
  authorization log, audit log).
- `tests/integration/meat_processing/test_meat_processing_bootstrap.py` —
  migración 187 registrada en orden estricto tras la 186; `migrations.engine.up()`
  completo (bootstrap real, no solo el módulo de migración aislado) crea las
  tablas del núcleo; `PRAGMA foreign_key_check` limpio; bootstrap idempotente
  (segunda corrida no duplica el registro en `schema_migrations`).
- `tests/architecture/test_meat_processing_repositories_never_commit.py` —
  disciplina de capas (commit/rollback solo en UoW; DDL solo en el módulo de
  esquema).

## Pendiente

- `MaterialRequirement`, work centers/recursos, incidencias, reprocesos,
  empaque, etiquetas, genealogía y tablas de sacrificio — fases posteriores
  (PROC-7, PROC-11 a PROC-13, PROC-17 a PROC-19, PROC-24), cada una con su
  propia migración aditiva sobre este mismo esquema.
- FKs cross-context (`product_id` → Productos, `branch_id`/`warehouse_id` →
  Inventario) se validan a nivel de aplicación por ahora; podrían añadirse como
  FKs de esquema una vez que el orden de migraciones entre bounded contexts esté
  formalmente garantizado.
- `backend/application/meat_processing/composition.py` (Use Case factory,
  patrón `InventoryUseCaseFactory`) — PROC-6+.
