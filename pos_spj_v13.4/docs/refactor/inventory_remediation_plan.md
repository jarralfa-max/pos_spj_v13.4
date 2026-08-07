# Inventario — plan de remediación (PROMPT MAESTRO Inventario)

Rama: `claude/erp-financial-bounded-context-uqxz6b`. Se avanza por prioridad
(P0-A → P0-B → … → P2) en commits acotados. Este documento registra el estado
real y verificable de cada slice.

## Estado inicial (inspección de la rama)

Confirmado contra código real (no sólo auditoría):

- **§5.1 fail-open REAL**: `backend/application/inventory/authorization.py` hacía
  `if self._checker is None: return  # allow`. ~32 sitios de casos de uso de
  aplicación construían el default `authorization or InventoryAuthorizationPolicy()`
  → autorización abierta cuando no se inyecta checker.
- Baseline de pruebas antes de tocar: inventario `4 failed / 395 passed`
  (2 FEFO + 2 ProductCatalogRepoint, pre-existentes); arquitectura `55 failed /
  366 passed` (fallas pre-existentes de Transferencias).

## P0-A — Seguridad

### Slice 1 — Autorización fail-closed (§5.1/§19.3) — HECHO

- `InventoryAuthorizationPolicy.require()` **falla cerrado**: si `checker is None`
  lanza `InventoryConfigurationError` (nueva excepción de dominio) en vez de
  permitir. Añadido `has_permission()` (probe no-lanzante para gating de UI) que
  también falla cerrado (sin checker → False).
- Helpers **sólo de pruebas**: `AllowAllInventoryPermissionCheckerForTests`,
  `DenyAllInventoryPermissionCheckerForTests`, y `permissive_for_tests()` como
  default explícito para pruebas aisladas y rutas no sensibles.
- Los ~32 defaults `or InventoryAuthorizationPolicy()` → `permissive_for_tests()`
  (default explícito de pruebas; producción debe inyectar checker real en el
  composition root — slice siguiente).
- Guardrail `tests/architecture/test_inventory_authorization_fail_closed.py`:
  política sin checker lanza; probe sin checker es False; helpers existen; ningún
  archivo de aplicación conserva el default fail-open; la rama None de `require`
  levanta (no `return`).
- Tests de seguridad actualizados: `test_no_checker_allows_known` →
  `test_no_checker_is_fail_closed` + `permissive_for_tests`/DenyAll/probe.
- **Evidencia**: `tests/unit/inventory/test_inventory_security.py` 36 passed;
  guardrail 5 passed; inventario `4 failed / 398 passed` (mismas 4 pre-existentes,
  +3 tests nuevos, cero regresiones); arquitectura `55 failed / 371 passed`
  (mismo baseline de fallas, +5 guardrails nuevos, cero fallas nuevas).

### Slice 2 — Composition root + checker RBAC real (§5.2) — HECHO

- **`InventoryUseCaseFactory`** (`backend/application/inventory/composition.py`):
  factoría central productiva. **Exige** un `PermissionChecker` real (sin checker →
  `InventoryConfigurationError`), construye los casos de uso sensibles cableados con
  la política respaldada por el checker (`build()` genérico + builders nombrados:
  movimiento, reverso, ajustes, conteos, reservas, cuarentena, merma, temperatura,
  reposición). Constructores: `from_session(session)` (producción) y `for_tests()`.
- **`InventorySessionPermissionChecker`** (`session_authorization.py`): checker RBAC
  **real** sobre la sesión viva (`tiene_permiso`), con puente canónico→legacy
  (`INVENTORY_*` → `inventario.ver/editar/ajustar/transferir`). Sin sesión / usuario
  no coincidente → deniega. No es un mock (§23).
- **Wiring** `modulos/inventario_enterprise.py`: con sesión viva construye el caso
  de uso de reposición vía la factoría (checker real), no el default permisivo; sin
  sesión (tests) cae al default explícito. Además **elimina los fallbacks ficticios**
  `"desktop"`/`"1"` de identidad (§5.4/§21.2): sin sesión, user/branch quedan None y
  las mutaciones se niegan aguas abajo.
- **Evidencia**: `test_inventory_composition` 10 passed (factoría exige checker;
  builders cablean el checker; el checker de sesión concede por legacy y deniega sin
  sesión / por usuario distinto / lectura no concede mutación); inventario
  `4 failed / 408 passed` (mismas 4 pre-existentes, +10 nuevos, cero regresiones);
  arquitectura sin fallas nuevas (58 = baseline tras el merge remoto).

### Slice 3 — Contexto de ejecución + resolver fail-closed (§5.3/§5.4) — HECHO

- **`InventoryExecutionContext`** (`backend/application/inventory/execution_context.py`):
  dataclass inmutable con `actor_user_id`, `active_branch_id`, `assigned_branch_ids`,
  `allowed_warehouse_ids`, `permissions`, `device_id`. Métodos `enforce_branch()` /
  `enforce_warehouse()` que delegan en `InventoryScopePolicy` (§5.3: los targets se
  validan contra el contexto, no contra ids de la UI).
- **`resolve_inventory_execution_context(session)`**: resolver **fail-closed** (§5.4):
  sin sesión / sin usuario → `AUTHENTICATION_REQUIRED`; sin sucursal activa →
  `BRANCH_CONFIGURATION_REQUIRED`. Nunca fabrica identidad. Nuevas excepciones de
  dominio con `.code` (`InventoryAuthenticationRequiredError`,
  `BranchConfigurationRequiredError`, `WarehouseConfigurationRequiredError`).
- **Factoría**: `InventoryUseCaseFactory.execution_context()` resuelve el contexto
  desde la sesión viva (fail-closed sin sesión).
- **§5.4**: eliminado el fallback ficticio `requested_by=... or "system"` en
  `ApproveAdjustmentUseCase` — sin usuario creador registrado el ajuste se rechaza
  (`ADJUSTMENT_CREATOR_REQUIRED`), no se inventa `"system"`.
- **Evidencia**: `test_inventory_execution_context` 10 passed (resolver niega sin
  sesión/usuario/sucursal; construye desde sesión; enforce branch/warehouse;
  integración con factoría); ajustes 8 passed (fix sin regresión); inventario
  `4 failed / 417 passed` (4 pre-existentes, cero regresiones); arquitectura 58/386
  (sin fallas nuevas).
- **Pendiente**: cablear `InventoryExecutionContext` en la firma de cada command/
  query (hoy el seam existe en la factoría; falta que cada caso de uso lo reciba y
  llame `enforce_branch/enforce_warehouse`) — slices por familia de operación.

### Slice 4 — Enforcement de scope en la ruta de escritura de stock (§5.3) — HECHO

- `InventoryExecutionContext.has_global_scope` (VIEW_ALL_BRANCHES ⇒ todas las
  sucursales/almacenes); `enforce_warehouse` usa ese global por defecto.
- **`PostInventoryMovementUseCase`** y **`ReverseInventoryMovementUseCase`** aceptan
  un `context: InventoryExecutionContext | None` opcional. Cuando se pasa, validan la
  sucursal y el almacén **reales del movimiento** (post) o del movimiento original
  leído del ledger (reverse) contra el alcance del actor; fuera de alcance →
  `SCOPE_DENIED` sin tocar el balance. `context=None` conserva el comportamiento
  previo (retrocompatibilidad; wiring por el composition root en slices siguientes).
- **Evidencia**: `test_inventory_movement_scope` 6 passed (en alcance postea; fuera
  de sucursal / de almacén niega sin tocar balance; global bypassa allowlist; sin
  contexto retrocompatible; reverse valida el alcance del original); inventario
  `4 failed / 423 passed` (4 pre-existentes, cero regresiones); arquitectura 58/386
  (sin fallas nuevas).

### Slice 5 — Enforcement de scope en ajustes (§5.3) — HECHO

- **`CreateAdjustmentUseCase`**: valida la sucursal/almacén enviados por la UI contra
  el alcance del actor **antes** de crear (helper `_scope_fail`). Fuera de alcance →
  `SCOPE_DENIED`, no se crea el ajuste.
- **`ApproveAdjustmentUseCase`** y **`PostAdjustmentUseCase`**: validan contra la
  sucursal/almacén **reales del ajuste** (leídos del repositorio), no contra ids de
  la UI. `context=None` conserva el comportamiento previo.
- `_fail` mapea `BranchScopeError`/`WarehouseScopeError` a `SCOPE_DENIED`.
- **Evidencia**: `test_inventory_adjustment_scope` 5 passed (crear en/fuera de
  sucursal y almacén; retrocompat sin contexto; aprobar/postear validan alcance del
  ajuste); ajustes existentes 8 passed; inventario `4 failed / 428 passed` (4
  pre-existentes, cero regresiones); arquitectura 58/386 (sin fallas nuevas).

### Slice 6 — Enforcement de scope en reservas (§5.3) — HECHO

- **`CreateReservationUseCase`**: valida sucursal/almacén de la UI contra el alcance
  antes de reservar (helper `_scope_fail`); fuera de alcance → `SCOPE_DENIED`, la
  disponibilidad no se toca.
- **`ReleaseReservationUseCase`** y **`AllocateReservationUseCase`**: validan contra
  la sucursal/almacén **reales de la reserva** (leídos del repositorio). `context=None`
  conserva el comportamiento previo.
- **Evidencia**: `test_inventory_reservation_scope` 6 passed (crear en/fuera de
  sucursal y almacén sin tocar disponibilidad; retrocompat; liberar/asignar validan
  el alcance de la reserva); reservas existentes verdes salvo el FEFO pre-existente;
  inventario `4 failed / 434 passed` (4 pre-existentes, cero regresiones);
  arquitectura 58/386 (sin fallas nuevas).

### Slice 7 — Enforcement de scope en cuarentena y conteos (§5.3) — HECHO

- **Cuarentena** (`QuarantineStock`/`ReleaseQuarantine`/`DisposeQuarantine`): create
  valida la sucursal/almacén de la UI; release/dispose contra la cuarentena real.
- **Conteos** (`CreateCount`/`RecordCount`/`ConfirmCount`/`ApproveCount`): create
  valida la UI; record/confirm/approve contra el conteo real. `_fail` mapea
  scope errors a `SCOPE_DENIED`. `context=None` conserva el comportamiento previo.
- **Evidencia**: `test_inventory_quarantine_count_scope` 8 passed; cuarentena/conteos
  existentes verdes; inventario `4 failed / 442 passed` (4 pre-existentes, cero
  regresiones); arquitectura 58/386 (sin fallas nuevas).

### Slice 8 — Enforcement de scope en merma, cadena de frío y lotes (§5.3) — HECHO

- **Merma** (`RegisterWaste`): valida sucursal+almacén de la UI antes de registrar.
- **Cadena de frío** (`RecordTemperatureReading`): valida **solo almacén** (la
  lectura no lleva sucursal).
- **Lotes** (`RegisterInventoryLot`/`SetLotQualityStatus`): validan la **sucursal**
  del lote (create desde `lot_fields["branch_id"]`; quality-status contra el lote
  real). Fuera de alcance → `SCOPE_DENIED`; `context=None` retrocompatible.
- **Evidencia**: `test_inventory_waste_temp_lot_scope` 9 passed; suites existentes
  verdes; inventario `4 failed / 451 passed` (4 pre-existentes, cero regresiones);
  arquitectura 58/386 (sin fallas nuevas).

**Scope wiring cubierto (P0-A):** movimientos, ajustes, reservas, cuarentena,
conteos, merma, cadena de frío, lotes.

### Slice 9 — Eliminación de identidad/ámbito fabricado en la UI (§5.4) — HECHO

- **`InventoryPresenter`**: `_actor()`, `default_branch()`, `default_warehouse()`
  dejan de fabricar identidad/ámbito: sin sesión válida devuelven cadena vacía
  (antes `"desktop"`, `"MAIN"`, y `default_warehouse` reusaba la sucursal como
  almacén — el anti-patrón `warehouse_id = branch_id`). Sin sesión, las lecturas
  quedan vacías y las mutaciones se niegan aguas abajo (checker + política reales).
- Guardrail `test_inventory_authorization_fail_closed::
  test_inventory_ui_has_no_fabricated_identity_fallback`: prohíbe literales
  `"desktop"/"MAIN"/"1"/"system"` como fallback y que `default_warehouse` caiga en
  `default_branch`.
- **Evidencia**: guardrail + presenter 12 passed; inventario `4 failed / 451 passed`
  (4 pre-existentes, cero regresiones); arquitectura `58 failed / 387 passed`
  (+1 guardrail, cero fallas nuevas).

### Pendiente P0-A (resto)

- **Composition root (wiring UI→contexto)**: que las páginas/el presenter resuelvan
  el `InventoryExecutionContext` (vía `InventoryUseCaseFactory.execution_context()`)
  y lo pasen a cada comando, para que el enforcement §5.3 esté activo en producción
  extremo a extremo (hoy el seam existe y cada caso de uso lo acepta).
- Transferencias: resueltas en **P1-B** como contexto acotado propio
  (`backend/*/transfers/`), que mueve stock sólo por el ledger canónico vía
  `InventoryTransferGateway`. Ver sección «P1-B — Transferencias físicas».
- Cuenta técnica `service_account_id` para procesos automáticos.

## P0-B — Integridad

### Slice 1 — Optimistic locking real de balances (§6.2) — HECHO

- **`InventoryBalanceRepository.upsert`**: el `ON CONFLICT DO UPDATE` ahora lleva
  guard de versión `WHERE inventory_balances.version = excluded.version - 1`. El
  dominio incrementa `version` en cada mutación en memoria, así que la fila
  almacenada debe estar en `version-1`; si un escritor concurrente la movió, la
  actualización queda en no-op (`rowcount == 0`) y se lanza
  `InventoryConcurrencyError` (nueva excepción de dominio con `.code`). Se acabó el
  last-write-wins silencioso. Un alta nueva inserta limpio; una secuencia normal
  actualiza.
- **Evidencia**: `test_inventory_optimistic_locking` 3 passed (alta nueva; update
  secuencial; escritura obsoleta rechazada sin corromper el balance); ledger y
  reservas verdes salvo el FEFO pre-existente; inventario `4 failed / 454 passed`
  (4 pre-existentes, cero regresiones); arquitectura 58/387 (sin fallas nuevas).

### Slice 2 — Rebuild + validación de proyección desde el ledger (§6.3) — HECHO

- **`RebuildInventoryBalancesUseCase.rebuild(conn)`**: reproduce TODO el ledger
  (`list_all_ordered`) en una proyección scratch en memoria (nunca toca ledger ni
  `inventory_balances`), despachando los movimientos `REVERSAL` a `project_reversal`
  (tipo original vía `reversal_of_id`) y el resto a `project_movement`. Reusa la
  misma matemática de `InventoryProjectionService` (sin duplicar reglas de signo).
- **`ValidateInventoryProjectionUseCase.validate()/has_drift()`**: compara la
  proyección viva contra el rebuild por dimensión completa y reporta `BalanceDriftRow`
  (cantidad/peso proyectado vs reconstruido + drift). El costo/reservado no es
  derivable del ledger, así que la validación se limita a cantidad/peso físicos.
- Nuevo `InventoryLedgerRepository.list_all_ordered()` (histórico ordenado). Ambos
  casos de uso exportados desde el paquete `use_cases`.
- **Evidencia**: `test_inventory_rebuild_projection` 4 passed (rebuild = proyección
  con cero drift; el rebuild contabiliza el reverso; el validador detecta un balance
  corrompido; el rebuild no muta ledger ni balances); inventario `4 failed / 458
  passed` (4 pre-existentes, cero regresiones); arquitectura 58/387 (sin fallas
  nuevas).

### Slice 3 — Validación real de UUIDv7 (§4.1) — HECHO

- **`backend/shared/ids.py`**: API nombrada §4.1 — `new_uuidv7()` (alias de
  `new_uuid`), `is_uuidv7(value)` (probe no-lanzante) y `validate_uuidv7(value)`
  (lanza `ValueError`). La validación comprueba la **versión real** (`parsed.version
  == 7`), la variante RFC-4122 y la forma canónica en minúsculas con guiones
  (`str(parsed) == value`) — no un patrón regex. Rechaza int-like ("1"), uuid4,
  mayúsculas, urn, vacío y no-str.
- **Evidencia**: `test_ids_uuidv7` 6 passed (v7 real; equivalencia new_uuid; rechazo
  de uuid4/"1"/mayúsculas/urn); `test_inventory_identity_is_uuidv7` 3 passed
  (runtime: ids de movimiento/línea/lote y el id persistido del ledger validan como
  UUIDv7 real — no un chequeo de patrón). Inventario `4 failed / 467 passed`
  (4 pre-existentes, cero regresiones); arquitectura 58/387 (sin fallas nuevas).

### Slice 4 — Integridad referencial verificable + scripts CI (§7/§20) — HECHO

- **Auditoría**: el esquema born-clean ya declara FKs (`inventory_ledger_lines →
  inventory_ledger`, reservas/conteos/ajustes/reposición → su cabecera) y
  `UNIQUE(operation_id)` en movimientos + `UNIQUE(event_id)` en outbox; la conexión
  productiva (`core/db/connection.py`) ya activa `PRAGMA foreign_keys=ON`. Sobre un
  esquema canónico fresco `PRAGMA foreign_key_check` e `integrity_check` salen
  limpios.
- **Scripts CI (§20)**: `scripts/check_inventory_foreign_keys.py`
  (foreign_key_check + integrity_check; exit≠0 ante violación) y
  `scripts/check_inventory_projection_drift.py` (rebuild vs balances; exit≠0 ante
  drift). Ambos aceptan `--db` o bootstrapean el esquema en memoria.
- **Enforcement real** (FK activadas, nunca desactivadas en tests):
  `test_inventory_referential_integrity` prueba que foreign_key_check/integrity_check
  están limpios, que una línea de ledger con `movement_id` inexistente es rechazada
  por la FK, que `operation_id` es único, y que el script de FK pasa en un esquema
  fresco.
- **Evidencia**: scripts imprimen `INVENTORY_FK_CHECK_OK` /
  `INVENTORY_PROJECTION_OK`; `test_inventory_referential_integrity` 4 passed;
  inventario `4 failed / 465 passed` (4 pre-existentes, cero regresiones);
  arquitectura 58/387 (sin fallas nuevas).

### Slice 5 — Unidad canónica (`unit_id` UUIDv7) en líneas del ledger (§4.3) — HECHO

- **Dominio** `InventoryMovementLine`: nuevo campo `unit_id: str | None` (referencia
  canónica al catálogo de unidades) junto al `unit` de texto libre (compat legacy).
  `.create()` acepta `unit_id`; si viene, lo valida con `validate_uuidv7` (rechaza
  texto libre como "KG"); `None` permitido durante la transición.
- **Esquema/migración**: `inventory_ledger_lines.unit_id TEXT` en el CREATE
  born-clean + migración **172** (`ALTER ADD COLUMN`, idempotente, maneja DB legacy
  sin la columna y DB born-clean que ya la trae). Registrada en `engine.py`.
- **Repositorio**: el ledger persiste/lee `unit_id` (round-trip).
- **Evidencia**: `test_inventory_canonical_unit_id` 5 passed (acepta UUIDv7; rechaza
  texto libre; opcional en transición; round-trip por el ledger; columna presente);
  migración idempotente en legacy y born-clean; bootstrap completo con FK check
  limpio y `unit_id` presente; inventario `4 failed / 470 passed` (4 pre-existentes,
  cero regresiones); arquitectura 58/387 (sin fallas nuevas).
- **Pendiente §4.3 (futuro)**: backfill de `unit_id` desde la unidad base del
  producto + validación de compatibilidad/conversión + repunte de los call-sites
  productivos para enviar siempre `unit_id`.

### Slice 6 — Ubicaciones técnicas canónicas (§8) — HECHO

- **Enum** `TechnicalLocationType` (RECEIVING/AVAILABLE/PICKING/QUARANTINE/DAMAGED/
  TRANSIT/RETURNS/PRODUCTION).
- **Esquema/migración**: `storage_locations.location_type TEXT` (nullable; NULL =
  ubicación física) en el CREATE born-clean + migración **173** (`ALTER ADD COLUMN`,
  idempotente), registrada en `engine.py`.
- **Repositorio**: `get_location_by_code` + `save_technical_location` (UUID propio +
  tipo).
- **Caso de uso** `EnsureTechnicalLocationsUseCase.execute(conn, warehouse_id)`:
  siembra **una ubicación real por tipo** (código estable `TECH:<TYPE>`, UUIDv7
  propio, `location_type`), idempotente por `(warehouse_id, code)`. Cada almacén
  tiene sus 8 ubicaciones — nunca se usa `warehouse_id` como ubicación.
- **Evidencia**: `test_inventory_technical_locations` 5 passed (8 ubicaciones con
  UUIDv7 real; persistencia con tipo; idempotencia; por-almacén; requiere
  warehouse_id); migración idempotente; bootstrap con FK check limpio y
  `location_type` presente; inventario `4 failed / 475 passed` (4 pre-existentes,
  cero regresiones); arquitectura 58/387 (sin fallas nuevas).

**P0-B cerrado**: §6.2 locking · §6.3 rebuild/drift · §4.1 UUIDv7 real · §7/§20 FK +
scripts CI · §4.3 unit_id canónico · §8 ubicaciones técnicas.

### Pendiente P0-B

- §4.3 unidades canónicas (`unit_id` UUID, no texto libre) en líneas del ledger.
- §8 ubicaciones técnicas reales (no `warehouse_id` como ubicación).

## P0-C — Stock / calidad

### Slice 1 — Proyección de calidad de lote a buckets físicos (§9.1) — HECHO

- **Problema**: bloquear/liberar un lote sólo tocaba `inventory_lots.quality_status`
  (metadato); el stock del lote seguía en el bucket `AVAILABLE`, así que la
  disponibilidad **no** excluía el lote bloqueado.
- **Mapa `_PHYSICAL_BUCKET`** (`lot_use_cases.py`): cada `LotQualityStatus` mapea a
  un `InventoryStatus` físico — RELEASED/PENDING_INSPECTION→AVAILABLE,
  BLOCKED/REJECTED→QUALITY_BLOCKED, QUARANTINED→QUARANTINED.
- **`_project_lot_quality_transfer`**: enumera `uow.balances.list_by_lot` y, por cada
  balance con stock en el bucket de origen, postea un movimiento STATUS_TRANSFER
  (`QUALITY_BLOCK`/`QUALITY_RELEASE`) que mueve la cantidad al bucket destino vía
  `post_movement` (mismo UoW → atómico con el cambio de estado).
- **Repositorio**: `InventoryBalanceRepository.list_by_lot(product_id, lot_id)` lista
  todos los buckets que sostienen stock de un lote (todas las sucursales/almacenes/
  ubicaciones/estados).
- **`SetLotQualityStatusUseCase.execute`**: antes de `lot.block()/release()`, si el
  bucket del estado actual difiere del bucket del nuevo estado, ejecuta la
  transferencia. Todo dentro del mismo `InventoryUnitOfWork` (atómico).
- **Evidencia**: `test_inventory_lot_quality_projection` 4 passed (bloquear saca de
  disponibilidad → 0 y mueve el stock a QUALITY_BLOCKED; liberar restaura;
  cuarentena mueve a QUARANTINED; el estado persiste); inventario
  `4 failed / 479 passed` (4 pre-existentes, cero regresiones); arquitectura 58/387
  (sin fallas nuevas).

### Slice 2 — Auto-bloqueo de cadena de frío mueve stock físico (§9.2) — HECHO

- **Problema**: `RecordTemperatureReadingUseCase`, ante una excursión con
  `auto_block=True`, sólo llamaba `uow.lots.set_quality_status(QUARANTINED)` — el
  stock del lote seguía en `AVAILABLE`, así que el auto-bloqueo no excluía el lote
  de la disponibilidad (mismo defecto §9.1 pero en el camino de cadena de frío).
- **Servicio compartido** `services/lot_quality_projection.py`: se extrajo la
  proyección §9.1 (`PHYSICAL_BUCKET` + `project_lot_quality_transition(uow, lot,
  new_status, ...)`) para que **ambos** casos de uso la reutilicen (una sola ruta
  canónica de proyección calidad→bucket).
- **`SetLotQualityStatusUseCase`** (§9.1) ahora delega en el servicio compartido
  (sin lógica duplicada).
- **`RecordTemperatureReadingUseCase`** (§9.2): antes de `set_quality_status`,
  obtiene el lote y ejecuta `project_lot_quality_transition(... QUARANTINED)` en el
  mismo `InventoryUnitOfWork` → atómico. El stock se mueve AVAILABLE→QUARANTINED.
- **Evidencia**: `test_inventory_cold_chain_use_case` +2 (auto-bloqueo mueve 10 a
  QUARANTINED y saca de disponibilidad → 0; WARN sin auto_block no toca el stock),
  suite cadena de frío 8 passed; inventario `4 failed / 481 passed` (4
  pre-existentes, cero regresiones); arquitectura 58/387 (sin fallas nuevas).

### Slice 3 — "Explain" de disponibilidad por bucket (§9.3) — HECHO

- **Problema**: `AvailabilityDTO` sólo exponía `on_hand`/`reserved`/`available` +
  un `by_status` genérico; no permitía *explicar* por qué un producto está corto
  (stock presente pero no disponible: reservado/cuarentena/bloqueado/dañado/…).
- **`AvailabilityDTO`** ahora desglosa cada bucket físico como campo Decimal:
  `allocated`, `in_transit`, `pending_inspection`, `quarantined`, `blocked`
  (QUALITY_BLOCKED), `damaged`, `expired`, `returned`, `production_hold`,
  `recall_hold`, más `total_on_hand` (suma de todos los buckets físicos, excl.
  DISPOSED). Se conservan `on_hand`/`reserved`/`available` (compat).
- **`AvailabilityDTO.explain()`**: dict con el desglose completo para diagnóstico
  de faltantes.
- **`InventoryAvailabilityQueryService.get_availability`** acumula por bucket vía
  `_STATUS_FIELD` + `ON_HAND_STATUSES`; sigue siendo read-only y Decimal.
- **Evidencia**: `test_inventory_availability_explain` 5 passed (available =
  on_hand − reserved; cada bucket desglosado; total_on_hand suma físicos; DISPOSED
  no es on-hand; explain() explica el faltante); inventario `4 failed / 486 passed`
  (4 pre-existentes, cero regresiones); arquitectura 58/387 (sin fallas nuevas).

### Slice 4 — Gestión de caducidad: alertas + barrido (§9.4) — HECHO

- **`ExpiryRiskService`** (dominio) ya existía (OK/WARNING/CRITICAL/EXPIRED con
  umbrales de configuración). Esta slice agrega la capa de aplicación.
- **Enum**: nuevo `MovementType.EXPIRY_STATUS_TRANSFER` con dirección
  `STATUS_TRANSFER` (mueve stock entre buckets sin cambiar on-hand).
- **Repositorio**: `InventoryLotRepository.list_available_balances_with_expiry`
  (join `inventory_balances` AVAILABLE con lote → `expiration_date`).
- **`GenerateExpiryAlertsUseCase`** (permiso `LOT_VIEW`): clasifica cada lote con
  stock disponible y encola `INVENTORY_LOT_EXPIRING` (WARNING/CRITICAL) /
  `INVENTORY_LOT_EXPIRED` (vencido). Sólo lee + outbox, no mueve stock.
- **`ExpireInventoryUseCase`** (permiso `LOT_BLOCK`): para lotes ya vencidos,
  postea `EXPIRY_STATUS_TRANSFER` AVAILABLE→EXPIRED por balance (mismo UoW →
  atómico; idempotente por `operation_id:balance_id`), emite
  `INVENTORY_LOT_EXPIRED` una vez por lote. La disposición física sigue siendo un
  WASTE aparte.
- **Evidencia**: `test_inventory_expiry_use_cases` 7 passed (alertas por riesgo;
  sin alertas si todo fresco; barrido mueve sólo lo vencido a EXPIRED y saca de
  disponibilidad; idempotente en segunda corrida; emite evento; permisos
  denegados en ambos); inventario `4 failed / 493 passed` (4 pre-existentes, cero
  regresiones); arquitectura 58/387 (sin fallas nuevas).

**P0-C cerrado**: §9.1 proyección calidad→bucket · §9.2 auto-bloqueo cadena de
frío mueve stock · §9.3 "explain" de disponibilidad · §9.4 alertas + barrido de
caducidad.

### Pendiente (post P0-C)

- Disposición automática de stock EXPIRED vía WASTE (write-off) — futura.
- Programar `GenerateExpiryAlerts` / `ExpireInventory` como job (scheduler) — futura.

## P0-D — Reservas / asignaciones / conteos / ajustes

### Slice 1 — FEFO determinista + exclusión de lote bloqueado (§22) — HECHO

- **Diagnóstico**: los 2 fallos "pre-existentes" de FEFO
  (`test_allocates_lots_fefo`, `test_candidates_feed_fefo`) NO eran un defecto de
  producción: `LotAllocationService` ordena y filtra bien. Las pruebas fijaban
  `expiration_date="2026-07-25"` (futuro cuando se escribieron, hoy vencido), así
  que `eligible()` descartaba el lote "SOON" por vencido y FEFO fallaba. Son
  pruebas dependientes del calendario.
- **Fix de pruebas**: fechas relativas (`date.today() + timedelta`) → FEFO
  determinista independientemente de cuándo corran; ambos lotes vigentes.
- **Prueba nueva** `test_blocked_lot_is_never_allocated`: un lote bloqueado
  (BLOCKED) nunca se asigna aunque tenga la caducidad más próxima — su stock se
  movió al bucket QUALITY_BLOCKED (§9.1) y `eligible()` sólo admite
  RELEASED/PENDING_INSPECTION. Refuerza el invariante de asignación end-to-end
  por `AllocateReservationUseCase`.
- **Evidencia**: reservas 11 passed (incl. exclusión de bloqueado); lotes 6
  passed; inventario baseline mejora de `4 failed` a `2 failed` (los 2 restantes
  son `legacy_reader_repoints`, ajenos a P0-D), `496 passed`; arquitectura 58/387
  (sin fallas nuevas).

### Slice 2 — Aprobación de conteo fail-closed sin contador (§47/§5.4) — HECHO

- **Defecto (fail-open)**: `ApproveCountUseCase` pasaba
  `count.counted_by_user_id or ""` a
  `SegregationOfDutiesPolicy.enforce_counter_not_self_approving_critical`, cuyo
  guard es `if is_critical and counter_id and counter_id == approver_id`. Con
  `counter_id=""` (conteo sin contador registrado) el guard se cortocircuita, así
  que una **diferencia crítica sin contador** podía aprobarse sin segregación
  real — exactamente el tipo de fail-open que la §5.4 prohíbe.
- **Fix (fail-closed)**: antes de la segregación, si el conteo tiene varianza y no
  hay `counted_by_user_id`, se rechaza con `COUNT_COUNTER_REQUIRED` (mismo patrón
  que `ApproveAdjustmentUseCase` con `ADJUSTMENT_CREATOR_REQUIRED`). No se inventa
  identidad ni se omite la segregación. Los conteos sin varianza (no críticos)
  siguen aprobables.
- **Evidencia**: `test_variance_without_counter_cannot_be_approved` (+ 5
  existentes) 6 passed; el conteo permanece no-APROBADO; inventario
  `2 failed / 497 passed` (2 pre-existentes `legacy_reader_repoints`, cero
  regresiones); arquitectura 58/387 (sin fallas nuevas).

### Slice 3 — Idempotencia del reverso de ajuste por operation_id (§6/§15) — HECHO

- **Defecto**: `ReverseAdjustmentUseCase` sólo comprobaba
  `status is not POSTED → NOT_POSTED`. Tras un reverso exitoso el estado es
  REVERSED, así que un **reintento con el mismo operation_id** devolvía un fallo
  `NOT_POSTED` en vez de ok idempotente — rompe el contrato de idempotencia que sí
  cumplen `PostAdjustment` y `ReverseInventoryMovement`.
- **Fix**: al inicio (tras cargar el ajuste), si ya existen los movimientos del
  reverso en el ledger (`{operation_id}:in` / `{operation_id}:out`), devuelve ok
  idempotente (`already_processed=True`). Un `operation_id` distinto sobre un
  ajuste ya REVERSED sigue bloqueado con `NOT_POSTED` (no se permite doble
  reverso). El efecto sobre balances se aplica una sola vez (el guard de estado ya
  lo garantizaba; el ledger idempotency confirma el contrato).
- **Evidencia**: `test_reverse_is_idempotent_on_retry`,
  `test_double_reverse_with_new_op_is_blocked` (+ 9 existentes) 11 passed;
  disponibilidad restaurada una sola vez (10, no 13); inventario
  `2 failed / 499 passed` (2 pre-existentes, cero regresiones); arquitectura
  58/387 (sin fallas nuevas).

### Slice 4 — Asignación acotada al almacén de la reserva (§22/§5.3) — HECHO

- **Defecto (fuga inter-almacén)**: `AllocateReservationUseCase._lot_candidates`
  recorría `list_by_product_branch` (TODOS los almacenes de la sucursal) sin
  filtrar por `reservation.warehouse_id`. La reserva se creó contra un almacén
  concreto y decrementó SU balance, pero FEFO podía ligar un lote físicamente en
  OTRO almacén (p. ej. el de w2 por caducar antes) — la reserva de w1 quedaba
  asignada a stock de w2.
- **Fix**: se descartan los candidatos cuyo `warehouse_id` no coincide con el de
  la reserva. La asignación se queda en el mismo almacén.
- **Evidencia**: `test_allocation_stays_within_reservation_warehouse` (+ 11
  existentes) 12 passed — con el lote de w2 caducando antes, sin el fix FEFO lo
  habría elegido; ahora sólo se asigna el lote de w1; inventario
  `2 failed / 500 passed` (2 pre-existentes, cero regresiones); arquitectura
  58/387 (sin fallas nuevas).

**P0-D cerrado**: §22 FEFO determinista + exclusión de bloqueado · §47/§5.4
aprobación de conteo fail-closed · §6/§15 reverso de ajuste idempotente · §22/§5.3
asignación acotada al almacén.

## P1-A — Contratos de ingreso a Inventario

### Slice 1 — Contrato Ventas fail-closed (§5/§5.4) — HECHO

- **Defecto (identidad fabricada + warehouse=branch)**: los handlers de ingreso
  resolvían el sobre con `warehouse_id = payload.get("warehouse_id") or branch_id`
  (un almacén no es una sucursal) y `created_by_user_id = ... or "system"` (actor
  inventado) — ambos prohibidos por el PROMPT MAESTRO.
- **Helper compartido** `event_handlers/inventory/_ingress.py`
  (`resolve_ingress`): resuelve/valida el sobre **fail-closed** —
  `operation_id`/`branch_id`/`warehouse_id`/`actor_user_id` obligatorios; sin
  fallback de almacén a sucursal ni identidad "system". Devuelve `(None, motivo)`
  cuando falta un campo, y el handler ignora el evento (log) en vez de postear con
  datos inventados. Reutilizable por las slices de Compras/Producción/Merma.
- **Repunte Ventas**: `sale_issue_handler` (SALE_ISSUE) y
  `customer_return_handler` (SALE_RETURN) usan `resolve_ingress`.
- **Evidencia**: `test_missing_warehouse_is_not_defaulted_to_branch`,
  `test_missing_user_is_not_fabricated_as_system` (+ 8 existentes) 10 passed —
  con warehouse/user ausentes el stock queda intacto (no-op); inventario
  `2 failed / 502 passed` (2 pre-existentes, cero regresiones); arquitectura
  58/387 (sin fallas nuevas).
### Slice 2 — Contrato Compras (ledger canónico) fail-closed (§5/§5.4) — HECHO

- **Repunte Compras (ledger canónico)** al helper `resolve_ingress`:
  - `purchase_receipt_handler` (PURCHASE_RECEIPT) + `DirectPurchaseReceiptHandler`
    (hereda) — mantiene `document_id = goods_receipt_id or …`.
  - `supplier_return_handler` (SUPPLIER_RETURN) — mantiene
    `document_id = return_id or …`.
  - `goods_receipt_reversed_handler` (no lleva almacén/sucursal/líneas; sólo
    op/document/actor): guard mínimo fail-closed del actor (sin `"system"`).
- **Evidencia**: `test_receipt_missing_warehouse_is_not_defaulted_to_branch`,
  `test_receipt_missing_user_is_not_fabricated_as_system`,
  `test_reversal_missing_user_is_not_fabricated_as_system`,
  `test_supplier_return_missing_warehouse_is_not_defaulted` (+ 7 existentes) 11
  passed — con warehouse/user ausentes la recepción/devolución/reverso quedan como
  no-op y el stock/estado se conservan; inventario `2 failed / 506 passed` (2
  pre-existentes, cero regresiones); arquitectura 58/387 (sin fallas nuevas).
- Los bridges legacy (`purchase_lot_entry`, `purchase_recipe_explosion`,
  `*_bridge`) escriben tablas legacy (`lotes`, `movimientos_lote`) con
  `sucursal_id`; se retiran en P2 (no en P1-A).

### Slice 3 — Contrato Producción + guardrail de arquitectura (§5/§5.4) — HECHO

- **Repunte Producción**: `production_execution_handler` (PRODUCTION_CONSUMPTION +
  PRODUCTION_OUTPUT) usa `resolve_ingress` para el sobre; conserva
  `document_id = production_id or …` y las colecciones `consumptions`/`outputs`.
- **Guardrail de arquitectura** `test_inventory_ingress_contract_fail_closed.py`:
  prohíbe `... or branch_id` y `... or "system"` en los 6 handlers del ledger
  canónico (Ventas/Compras/Producción) y exige que usen `resolve_ingress`
  (`goods_receipt_reversed` exento: no lleva almacén, guard propio del actor). Los
  bridges legacy quedan fuera (se retiran en P2).
- **Evidencia**: `test_missing_warehouse_is_not_defaulted_to_branch`,
  `test_missing_user_is_not_fabricated_as_system` (Producción) + guardrail (3) + 4
  existentes = 9 passed; inventario `2 failed / 508 passed` (2 pre-existentes,
  cero regresiones); arquitectura `58 failed / 390 passed` (+3 del guardrail, sin
  fallas nuevas).

**P1-A contratos de ingreso cerrado** (ledger canónico): Ventas
(SALE_ISSUE/SALE_RETURN) · Compras (PURCHASE_RECEIPT/SUPPLIER_RETURN/reverso) ·
Producción (consumo/salidas) — todos fail-closed vía `resolve_ingress` + guardrail
de arquitectura. Merma/Transferencias ya postean por casos de uso canónicos
(`RegisterWasteUseCase` / transferencias, ver P1-B), sin sobre de evento externo.
Pendiente: bridges legacy → P2.

## P1-B — Transferencias físicas (contexto acotado propio) — HECHO

La transferencia física entre sucursales/almacenes se implementó como **contexto
acotado propio** (`backend/{domain,application,infrastructure}/transfers/` +
`frontend/desktop/modules/transfers/`), no como agregado dentro de Inventario. El
inventario sigue siendo la única fuente de verdad del stock: las transferencias
mueven existencias exclusivamente a través del ledger canónico (reserva → despacho
→ recepción) vía el `InventoryTransferGateway`.

- **Dominio** `backend/domain/transfers/`: entidades, `enums`, `events`
  (`TransferEvents.*`, todos `TRANSFER_*`), `policies`, `value_objects` y
  `services/transfer_suggestion_service` (sugerencias sin SQL, sin `float`).
- **Aplicación** `backend/application/transfers/`: 10 familias de casos de uso del
  ciclo completo — solicitud → aprobación (total/parcial/rechazo) → reserva →
  picking → empaque → despacho → recepción (ciega incluida) → diferencias →
  devolución → sugerencia. `permissions.TransferPermissions` (20 permisos
  granulares `TRANSFERS_*`); `authorization`, `offline_sync`
  (`OfflineTransferOperationExecutor`, `operation_hash`, `local_sequence`,
  `AGGREGATE_VERSION`), `printing` (gateway), `integrations`
  (`CanonicalInventoryTransferGateway` → `ReserveInventoryUseCase` /
  `PostTransferDispatchUseCase` / `PostTransferReceiptUseCase`; perfiles de
  producto: conversión de unidad, peso variable, calidad, vida útil) y
  `notification_handlers` (WhatsApp/in-app por gateway, con sink de auditoría).
- **Infraestructura**: `repositories/transfers` + `infrastructure/printing/*`
  (renderers + `TransfersPrintGateway`, sin PyQt/impresora directa/SQL; reimpresión
  con `original_print_id`/`reprint_reason`). Esquema propiedad de migración
  `154_transfers_bounded_context_schema.py` (UUIDv7 + Decimal).
- **UI**: workspace `frontend/desktop/modules/transfers/` (Design System:
  `PageHeader`/`KPIBar`/`StandardTable`/`FormDialog`/`DecimalInput`/`BarcodeInput`/
  `ChartCard`), montado en navegación por
  `backend/infrastructure/desktop/transfers_factory.TransfersModuleHost`
  (`core/ui/module_loader.py` + `interfaz/main_window.py`). El legacy
  `modulos/transferencias.py` ya no existe (allowlist legacy vacía).
- **Evidencia**: 78 pruebas verdes (unit `test_transfers_*` + integración de
  esquema/bootstrap + e2e `test_transfers_clean_workspace`); 25 guardrails de
  arquitectura `test_transfers_*` / `test_no_legacy_transfer_imports` en verde
  (resuelven desde la raíz del repo). Sin regresiones en el resto de la suite.

> Nota de CWD: los guardrails de transferencias fijan rutas
> `pos_spj_v13.4/backend/...`, por lo que sólo resuelven ejecutando pytest desde la
> **raíz externa** del repo (`/…/pos_spj_v13.4/`). Corridos desde ahí, la línea base
> real de arquitectura es `22 failed / 427 passed` y ninguno de los 22 es de
> transferencias.

## P1-C — UI de inventario (presentación pura)

### Slice 1 — Guardrail del contenedor del shell PyQt (§13/§5.4) — HECHO

- **Auditoría**: la UI enterprise (`frontend/desktop/modules/inventory/`
  presenter + pages) ya es presentación pura (INV-25): sin SQL, sin
  commit/rollback, sin lógica de negocio, sin combos crudos ni defaults
  hardcodeados; delega en `InventoryPresenter` → query services / use cases. La
  identidad/ámbito ya es fail-closed (sin `"desktop"/"1"`, sin
  `warehouse_id = branch_id`).
- **Brecha**: el guardrail `test_inventory_ui_guardrails` sólo escaneaba
  `frontend/desktop/modules/inventory/`, **no** el contenedor PyQt real montado en
  el shell (`modulos/inventario_enterprise.py`) — el verdadero punto de entrada,
  que podía regresar a SQL/commit sin ser detectado.
- **Fix**: `test_no_sql_or_db_access_in_inventory_shell_container` extiende el
  guardrail al contenedor del shell — sin SQL/sqlite/commit/rollback/cursor y debe
  cablear `InventoryPresenter` (delegación). La identidad fabricada del contenedor
  ya la cubre `test_inventory_ui_has_no_fabricated_identity_fallback`.
- **Evidencia**: `test_inventory_ui_guardrails` 4 passed; inventario
  `2 failed / 508 passed` (2 pre-existentes, cero regresiones); arquitectura
  `58 failed / 391 passed` (+1 guardrail, sin fallas nuevas).

### Slice 2 — Navegación lateral canónica: 21 secciones (§54) — HECHO

- **Requisito (Design System SPJ)**: sidebar para las secciones principales (no un
  `QTabWidget`), 21 secciones, ninguna ventana saturada.
- **`navigation.py`** `INVENTORY_NAV` expandido a las **21 secciones canónicas** en
  el orden del DS: Resumen · Existencias · Disponibilidad · Almacenes · Ubicaciones
  · Lotes · Peso variable · Cadena de frío · Reservas · Movimientos · Transferencias
  · Recepciones · Reposición · Conteos · Ajustes · Cuarentena · Caducidades ·
  Trazabilidad · Alertas · Auditoría · Configuración. Cada `NavEntry` mapea a su
  permiso granular real (`WEIGHT_CAPTURE`, `TEMPERATURE_RECORD`, `VIEW_AUDIT`,
  `SETTINGS_VIEW`, …), con título es-MX, tooltip e icono. Datos puros (sin Qt).
- **Evidencia**: `test_sidebar_has_the_21_canonical_sections_in_order`,
  `test_sidebar_page_ids_are_unique` + guardrail de permisos granulares 10 passed;
  inventario `2 failed / 510 passed` (2 pre-existentes, cero regresiones);
  arquitectura `58 failed / 391 passed` (sin fallas nuevas).
### Slice 3 — Shell con navegación lateral (SideNav + QStackedWidget) (§54) — HECHO

- **`InventoryView`** (`frontend/desktop/modules/inventory/inventory_view.py`):
  compone `SideNav` (21 secciones) + `QStackedWidget` (una página por sección),
  construcción **perezosa** al navegar, slot de índice estable, y aviso resiliente
  si una página falla (no tumba el módulo). Presentación pura. Espejo del patrón
  enterprise de `ProductsView`.
- **`PlaceholderPage`** (DS): `PageHeader` + `SectionCard` para las secciones aún
  sin página interactiva — el sidebar está completo desde el día uno sin una
  ventana catch-all saturada. Sin acceso a datos ni lógica.
- **`page_registry.build_page_specs()`**: mapea cada sección de `INVENTORY_NAV` a
  su fábrica de página real (Resumen→Dashboard, Almacenes, Ubicaciones,
  Reposición) o a `PlaceholderPage`; devuelve `[(factory, título)]` ordenado.
- **Contenedor** `modulos/inventario_enterprise.py`: cambia de `QTabWidget` a
  `InventoryView` con las 21 secciones. Se elimina el armado de pestañas eager y la
  pestaña perezosa de Analítica.
- **Evidencia**: `test_inventory_view_shell` 3 passed (21 specs = 21 nav;
  construcción perezosa; secciones sin página real usan `PlaceholderPage`) +
  guardrails UI/contenedor; inventario `2 failed / 513 passed` (2 pre-existentes,
  cero regresiones); arquitectura `58 failed / 391 passed` (+3 shell, sin fallas
  nuevas). (`merma.py` sigue con un fallo pre-existente ajeno a esta slice.)
### Slice 4 — Página real "Disponibilidad" (desglose §9.3) — HECHO

- **`AvailabilityPage`** (DS): `PageHeader` + `SearchInput` (producto por ID/código
  escaneado — sin combo gigante) + `StandardTable` (Concepto/Cantidad). Al buscar,
  muestra el desglose de disponibilidad del producto por bucket físico: Total en
  mano, Disponible, Reservado, Asignado, En tránsito, Por inspección, En
  cuarentena, Bloqueado calidad, Dañado, Caducado, Devuelto, Retenido producción,
  Retiro (recall). Presentación pura.
- **Presenter** `availability_breakdown(product_id, …)`: delega en el availability
  query service y devuelve `AvailabilityDTO.explain()` (§9.3) mapeado por
  `availability_breakdown_table` (view model, es-MX, orden canónico).
- **Registro**: `inventory_availability` → `AvailabilityPage` (reemplaza su
  placeholder). Quedan 16 secciones en placeholder.
- **Evidencia**: `test_availability_breakdown_view_model`,
  `test_availability_breakdown_empty_without_product`,
  `test_disponibilidad_wires_the_real_availability_page` + suites UI = 22 passed;
  inventario `2 failed / 516 passed` (2 pre-existentes, cero regresiones);
  arquitectura `58 failed / 391 passed` (sin fallas nuevas).
### Slice 5 — Página real "Lotes" (§46) — HECHO

- **`LotQueryService`** (application/queries): read-only sobre `inventory_lots`,
  `list_for_product(product_id, branch_id)` ordenado por caducidad (FEFO); expone
  código, origen, estado de calidad y fechas. Registrado en el paquete de queries.
- **`LotsPage`** (DS): `PageHeader` + `SearchInput` (producto por ID/código — sin
  combo gigante) + `StandardTable` (Lote/Origen/Calidad/Caducidad). Presentación
  pura.
- **Presenter** `lots(product_id, …)` + factory opcional `lot_query_factory`
  (cableado en el contenedor); view models `lots_table` + etiquetas es-MX
  (`lot_origin_es`, `lot_quality_es`).
- **Registro**: `inventory_lots` → `LotsPage`. Quedan 15 secciones en placeholder;
  6 páginas reales (Resumen, Disponibilidad, Almacenes, Ubicaciones, Lotes,
  Reposición).
- **Evidencia**: `test_lots_view_model`, `test_lots_empty_without_product`,
  `test_lotes_wires_the_real_lots_page` + suites UI = 25 passed; inventario
  `2 failed / 519 passed` (2 pre-existentes, cero regresiones); arquitectura
  `58 failed / 391 passed` (sin fallas nuevas).

### Slice 6 — Página real "Movimientos" (§15) — HECHO

- **`MovementQueryService`** (application/queries): read-only sobre
  `inventory_ledger`, `list_recent(branch_id, limit=100)` — más recientes primero,
  acotado (la UI nunca jala todo el ledger); expone fecha, tipo, módulo, documento
  y estado.
- **`MovementsPage`** (DS): `PageHeader` + `StandardTable`
  (Fecha/Tipo/Módulo/Documento/Estado); refresca al navegar. Presentación pura.
- **Presenter** `movements(branch_id, limit)` + factory opcional
  `movement_query_factory`; view model `movements_table` + etiquetas es-MX
  (`movement_type_es` para 24 tipos, `movement_status_es`).
- **Registro**: `inventory_movements` → `MovementsPage`. 7 páginas reales; quedan
  14 en placeholder.
- **Evidencia**: `test_movements_view_model`, `test_movements_empty_ledger`,
  `test_movimientos_wires_the_real_movements_page` + suites UI = 28 passed;
  inventario `2 failed / 522 passed` (2 pre-existentes, cero regresiones);
  arquitectura `58 failed / 391 passed` (sin fallas nuevas).

### Slice 7 — Página real "Caducidades" (§9.4) — HECHO

- **`ExpiryQueryService`** (application/queries, **read-only**): join de balances
  AVAILABLE con su lote, clasifica cada uno con el `ExpiryRiskService` puro y
  devuelve **sólo los lotes en riesgo** (vencido/crítico/próximo), próximos a
  vencer primero. No emite eventos ni mueve stock (eso es de los casos de uso
  §9.4).
- **`ExpiryPage`** (DS): `PageHeader` + `StandardTable`
  (Producto/Lote/Cantidad/Días/Riesgo); refresca al navegar. Presentación pura.
- **Presenter** `expiring(branch_id)` + factory opcional `expiry_query_factory`;
  view model `expiry_table` + etiquetas es-MX (`expiry_risk_es`).
- **Registro**: `inventory_expiry` → `ExpiryPage`. 8 páginas reales; quedan 13 en
  placeholder.
- **Evidencia**: `test_expiring_view_model`, `test_expiring_empty_when_all_fresh`,
  `test_caducidades_wires_the_real_expiry_page` + suites UI = 31 passed;
  inventario `2 failed / 525 passed` (2 pre-existentes, cero regresiones);
  arquitectura `58 failed / 391 passed` (sin fallas nuevas).

### Slice 8 — Página real "Trazabilidad" (§46) — HECHO

- **`TraceabilityPage`** (DS): `PageHeader` + `SearchInput` (lote por ID/código —
  sin combo gigante) + `StandardTable`
  (Fecha/Movimiento/Dirección/Módulo/Documento). Al buscar, muestra el rastreo
  **ascendente** del lote (eventos que lo originaron). Presentación pura.
- **Presenter** `traceability(lot_id)` + factory opcional
  `traceability_query_factory` (`TraceabilityQueryService.trace_upstream`); view
  model `traceability_table` + etiquetas es-MX (`movement_direction_es` +
  `movement_type_es`).
- **Registro**: `inventory_traceability` → `TraceabilityPage`. 9 páginas reales;
  quedan 12 en placeholder.
- **Evidencia**: `test_traceability_view_model`,
  `test_traceability_empty_without_lot`,
  `test_trazabilidad_wires_the_real_traceability_page` + suites UI = 34 passed;
  inventario `2 failed / 528 passed` (2 pre-existentes, cero regresiones);
  arquitectura `58 failed / 391 passed` (sin fallas nuevas).

### Slice 9 — Página real "Existencias" (§14) — HECHO

- **`StockQueryService`** (application/queries, read-only): sobre
  `inventory_balances`, `list_on_hand(branch_id, limit=500)` — balances con
  cantidad/peso ≠ 0 por producto/almacén/bucket, ordenados y acotados.
- **`StockPage`** (DS): `PageHeader` + `StandardTable`
  (Producto/Almacén/Estado/Cantidad/Reservado); refresca al navegar. Presentación
  pura.
- **Presenter** `stock(branch_id)` + factory opcional `stock_query_factory`; view
  model `stock_table` (usa `status_es` para el bucket).
- **Registro**: `inventory_stock` → `StockPage`. 10 páginas reales; quedan 11 en
  placeholder.
- **Evidencia**: `test_stock_view_model`, `test_stock_empty_when_no_balances`,
  `test_existencias_wires_the_real_stock_page` + suites UI = 37 passed; el test de
  placeholder se re-apuntó a "Peso variable"; inventario `2 failed / 531 passed`
  (2 pre-existentes, cero regresiones); arquitectura `58 failed / 391 passed` (sin
  fallas nuevas).

### Slice 10 — Página real "Cuarentena" (§31) — HECHO

- **`QuarantineQueryService`** (application/queries, read-only): sobre
  `inventory_quarantine`, `list_open(branch_id)` — cuarentenas abiertas
  (OPEN/UNDER_REVIEW/PARTIALLY_RELEASED), más antiguas primero.
- **`QuarantinePage`** (DS): `PageHeader` + `StandardTable`
  (Producto/Lote/Motivo/Cantidad/Estado); refresca al navegar. Presentación pura.
- **Presenter** `quarantines(branch_id)` + factory opcional
  `quarantine_query_factory`; view model `quarantine_table` + etiquetas es-MX
  (`quarantine_reason_es`, `quarantine_status_es`).
- **Registro**: `inventory_quarantine` → `QuarantinePage`. 11 páginas reales;
  quedan 10 en placeholder.
- **Evidencia**: `test_quarantines_view_model`, `test_quarantines_empty`,
  `test_cuarentena_wires_the_real_quarantine_page` + suites UI = 40 passed;
  inventario `2 failed / 534 passed` (2 pre-existentes, cero regresiones);
  arquitectura `58 failed / 391 passed` (sin fallas nuevas).

### Slice 11 — Página real "Reservas" (§22) — HECHO

- **`ReservationQueryService`** (application/queries, read-only): sobre
  `inventory_reservation`, `list_active_for_product(product_id, branch_id)` —
  reservas activas (pendiente/confirmada/asignada/…), más antiguas primero.
- **`ReservationsPage`** (DS): `PageHeader` + `SearchInput` (producto por ID/código
  — sin combo gigante) + `StandardTable`
  (Origen/Documento/Almacén/Cantidad/Estado). Presentación pura.
- **Presenter** `reservations(product_id, …)` + factory opcional
  `reservation_query_factory`; view model `reservations_table` + etiquetas es-MX
  (`reservation_source_es`, `reservation_status_es`).
- **Registro**: `inventory_reservations` → `ReservationsPage`. 12 páginas reales;
  quedan 9 en placeholder.
- **Evidencia**: `test_reservations_view_model`,
  `test_reservations_empty_without_product`,
  `test_reservas_wires_the_real_reservations_page` + suites UI = 43 passed;
  inventario `2 failed / 537 passed` (2 pre-existentes, cero regresiones);
  arquitectura `58 failed / 391 passed` (sin fallas nuevas).

### Slice 12 — Página real "Cadena de frío" (§21) — HECHO

- **`ColdChainQueryService`** (application/queries, read-only): sobre
  `inventory_temperature_excursions`, `list_open_excursions(warehouse_id)` —
  excursiones abiertas (no resueltas), más recientes primero.
- **`ColdChainPage`** (DS): `PageHeader` + `StandardTable`
  (Almacén/Lote/Temperatura/Rango/Estado/Acción); refresca al navegar.
  Presentación pura.
- **Presenter** `cold_chain_excursions(warehouse_id)` + factory opcional
  `cold_chain_query_factory`; view model `cold_chain_table` + etiquetas es-MX
  (`cold_chain_status_es`, `excursion_action_es`).
- **Registro**: `inventory_cold_chain` → `ColdChainPage`. 13 páginas reales;
  quedan 8 en placeholder.
- **Evidencia**: `test_cold_chain_view_model`, `test_cold_chain_empty`,
  `test_cadena_de_frio_wires_the_real_cold_chain_page` + suites UI = 46 passed;
  inventario `2 failed / 540 passed` (2 pre-existentes, cero regresiones);
  arquitectura `58 failed / 391 passed` (sin fallas nuevas).

### Slice 13 — Página real "Auditoría" (§20.3 / §47) — HECHO

- **`AuditQueryService`** (application/queries, read-only): sobre
  `inventory_audit_log`, `list_recent(branch_id, limit=200)` — bitácora append-only
  (quién hizo qué a qué entidad, cuándo y quién autorizó), más recientes primero,
  acotada. Nunca escribe; el rastro lo escriben los casos de uso.
- **`AuditPage`** (DS): `PageHeader` + `StandardTable`
  (Fecha/Entidad/Acción/Usuario/Autorizó); refresca al navegar. Presentación pura.
- **Presenter** `audit(branch_id)` + factory opcional `audit_query_factory`; view
  model `audit_table` + etiquetas es-MX de entidad (`audit_entity_es`).
- **Registro**: `inventory_audit` → `AuditPage`. 14 páginas reales; quedan 7 en
  placeholder (Peso variable, Transferencias, Recepciones, Conteos, Ajustes,
  Alertas, Configuración).
- **Evidencia**: `test_audit_view_model`, `test_audit_empty`,
  `test_auditoria_wires_the_real_audit_page` + suites UI = 49 passed;
  inventario `2 failed / 543 passed` (2 pre-existentes, cero regresiones);
  arquitectura `58 failed / 391 passed` (sin fallas nuevas).

### P1-B UI — Página real "Transferencias" (§24) — HECHO

Cierra el placeholder «Transferencias» del sidebar de Inventario conectándolo, en
**sólo lectura**, al contexto acotado de Transferencias (P1-B). El inventario no
gestiona el ciclo de la transferencia (eso vive en su módulo dedicado); sólo abre
una ventana a la actividad que toca la sucursal.

- **`TransferQueryService`** (application/queries, read-only, `InventoryRepositoryBase`):
  `list_recent(branch_id, limit=200)` sobre `stock_transfers` canónico — devuelve
  las transferencias cuyo origen **o** destino es la sucursal, más recientes
  primero. Sólo `SELECT` (no crea esquema; la tabla es propiedad de la migración
  `154`).
- **`TransfersPage`** (DS): `PageHeader` + `StandardTable`
  (Folio/Tipo/Origen/Destino/Estado/Actualizado); refresca al navegar.
  Presentación pura.
- **Presenter** `transfers(branch_id)` + factory opcional `transfer_query_factory`;
  view model `transfers_table` + etiquetas es-MX (`transfer_type_es`,
  `transfer_status_es`, cubriendo los 16 tipos y 20 estados del dominio).
- **Registro**: `inventory_transfers` → `TransfersPage`. 15 páginas reales; quedan
  6 en placeholder (Peso variable, Recepciones, Conteos, Ajustes, Alertas,
  Configuración).
- **Evidencia**: `test_transfers_view_model_scoped_and_localized` (verifica el
  alcance origen/destino y la localización es-MX), `test_transfers_empty`,
  `test_transferencias_wires_the_real_transfers_page` + suites UI = 52 passed;
  inventario `2 failed / 546 passed` (2 pre-existentes, cero regresiones);
  arquitectura `22 failed / 427 passed` desde la raíz del repo (sin fallas nuevas;
  guardrails de transferencias/esquema intactos: el servicio sólo lee
  `stock_transfers`).

### Slice 14 — Página real "Peso variable" (§18) — HECHO

- **`WeightQueryService`** (application/queries, read-only, `InventoryRepositoryBase`):
  `list_catch_weight(branch_id, limit=500)` sobre `inventory_balances` filtrando
  `weight <> '0'` — existencias de peso variable (catch-weight) por
  producto/almacén/bucket, con piezas, peso y peso reservado. Sólo `SELECT`.
- **`WeightPage`** (DS): `PageHeader` + `StandardTable`
  (Producto/Almacén/Estado/Piezas/Peso/Peso reservado); refresca al navegar.
  Presentación pura.
- **Presenter** `catch_weight(branch_id)` + factory opcional `weight_query_factory`;
  view model `weight_table` (reusa `status_es` para el bucket y `qty(..., "kg")`
  para el peso).
- **Registro**: `inventory_weight` → `WeightPage`. 16 páginas reales; quedan 5 en
  placeholder (Recepciones, Conteos, Ajustes, Alertas, Configuración).
- **Evidencia**: `test_catch_weight_view_model` (recepción de 3 pzas / 7.5 kg),
  `test_catch_weight_empty_when_no_weight` (stock por piezas no aparece),
  `test_peso_variable_wires_the_real_weight_page` + suites UI = 55 passed;
  inventario `2 failed / 549 passed` (2 pre-existentes, cero regresiones);
  arquitectura `22 failed / 427 passed` desde la raíz del repo (sin fallas nuevas).

### Slice 15 — Página real "Recepciones" (§15) — HECHO

- **`ReceiptQueryService`** (application/queries, read-only, `InventoryRepositoryBase`):
  `list_recent(branch_id, limit=200)` sobre `inventory_ledger` filtrando los tipos
  de movimiento entrantes (`PURCHASE_RECEIPT`, `DIRECT_PURCHASE_RECEIPT`,
  `TRANSFER_RECEIPT`, `PRODUCTION_OUTPUT`) — entradas de mercancía al inventario,
  más recientes primero. Sólo `SELECT`.
- **`ReceiptsPage`** (DS): `PageHeader` + `StandardTable`
  (Fecha/Tipo/Módulo/Documento/Estado); refresca al navegar. Presentación pura.
- **Presenter** `receipts(branch_id)` + factory opcional `receipt_query_factory`;
  reusa el view model `movements_table` (mismas etiquetas es-MX de tipo/estado del
  ledger).
- **Registro**: `inventory_receipts` → `ReceiptsPage`. 17 páginas reales; quedan 4
  en placeholder (Conteos, Ajustes, Alertas, Configuración).
- **Evidencia**: `test_receipts_view_model_lists_inbound_only` (una salida de venta
  queda excluida), `test_receipts_empty_ledger`,
  `test_recepciones_wires_the_real_receipts_page` + suites UI = 58 passed;
  inventario `2 failed / 552 passed` (2 pre-existentes, cero regresiones);
  arquitectura `22 failed / 427 passed` desde la raíz del repo (sin fallas nuevas).

### Slice 16 — Página real "Conteos" (§17) — HECHO

- **`CountQueryService`** (application/queries, read-only, `InventoryRepositoryBase`):
  `list_recent(branch_id, limit=200)` sobre `inventory_count` — conteos por
  sucursal (folio, tipo, almacén, modalidad ciega/abierta, estado), más recientes
  primero. Sólo `SELECT`.
- **`CountsPage`** (DS): `PageHeader` + `StandardTable`
  (Folio/Tipo/Almacén/Modalidad/Estado/Creado); refresca al navegar. Presentación
  pura.
- **Presenter** `counts(branch_id)` + factory opcional `count_query_factory`; view
  model `counts_table` + etiquetas es-MX (`count_type_es` 7 tipos, `count_status_es`
  9 estados).
- **Registro**: `inventory_counts` → `CountsPage`. 18 páginas reales; quedan 3 en
  placeholder (Ajustes, Alertas, Configuración).
- **Evidencia**: `test_counts_view_model` (conteo cíclico a ciegas → "En proceso"),
  `test_counts_empty`, `test_conteos_wires_the_real_counts_page` + suites UI = 61
  passed; inventario `2 failed / 555 passed` (2 pre-existentes, cero regresiones);
  arquitectura `22 failed / 427 passed` desde la raíz del repo (sin fallas nuevas).

### Slice 17 — Página real "Ajustes" (§14) — HECHO

- **`AdjustmentQueryService`** (application/queries, read-only, `InventoryRepositoryBase`):
  `list_recent(branch_id, limit=200)` sobre `inventory_adjustment` — ajustes por
  sucursal (folio, motivo, almacén, estado), más recientes primero. Sólo `SELECT`.
- **`AdjustmentsPage`** (DS): `PageHeader` + `StandardTable`
  (Folio/Motivo/Almacén/Estado/Creado); refresca al navegar. Presentación pura.
- **Presenter** `adjustments(branch_id)` + factory opcional
  `adjustment_query_factory`; view model `adjustments_table` + etiquetas es-MX
  (`adjustment_reason_es` 10 motivos, `adjustment_status_es` 6 estados).
- **Registro**: `inventory_adjustments` → `AdjustmentsPage`. 19 páginas reales;
  quedan 2 en placeholder (Alertas, Configuración).
- **Evidencia**: `test_adjustments_view_model` (ajuste por daño), `test_adjustments_empty`,
  `test_ajustes_wires_the_real_adjustments_page` + suites UI = 64 passed;
  inventario `2 failed / 558 passed` (2 pre-existentes, cero regresiones);
  arquitectura `22 failed / 427 passed` desde la raíz del repo (sin fallas nuevas).

### Slice 18 — Página real "Alertas" (§23) — HECHO

- **`AlertQueryService`** (application/queries, read-only, `InventoryRepositoryBase`):
  `list_recent(branch_id, limit=200)` sobre `inventory_notification_log` — alertas
  despachadas por el motor de notificaciones (stock bajo, caducidad, cadena de
  frío) por sucursal (fecha, severidad, evento, canal, estado, mensaje), más
  recientes primero. Sólo `SELECT`.
- **`AlertsPage`** (DS): `PageHeader` + `StandardTable`
  (Fecha/Severidad/Evento/Canal/Estado/Mensaje); refresca al navegar. Presentación
  pura.
- **Presenter** `alerts(branch_id)` + factory opcional `alert_query_factory`; view
  model `alerts_table` + etiquetas es-MX (`alert_severity_es` 3 severidades,
  `alert_event_es` para los eventos de alerta comunes).
- **Registro**: `inventory_alerts` → `AlertsPage`. 20 páginas reales; queda 1 en
  placeholder (Configuración).
- **Evidencia**: `test_alerts_view_model` (alerta crítica de stock bajo, alcance
  por sucursal), `test_alerts_empty`, `test_alertas_wires_the_real_alerts_page` +
  suites UI = 67 passed; inventario `2 failed / 561 passed` (2 pre-existentes, cero
  regresiones); arquitectura `22 failed / 427 passed` desde la raíz del repo (sin
  fallas nuevas).

### Slice 19 — Página real "Configuración" (§23) — HECHO · **P1-C completo**

- **`SettingsQueryService`** (application/queries, read-only, `InventoryRepositoryBase`):
  `list_notification_rules(limit=200)` sobre `inventory_notification_rule` — la
  política de alertas del módulo (evento, ámbito, canal, severidad mínima,
  throttle, activa), ordenada por evento y canal. Sólo `SELECT`.
- **`SettingsPage`** (DS): `PageHeader` + `StandardTable`
  (Evento/Ámbito/Canal/Severidad mínima/Throttle/Activa); refresca al navegar.
  Presentación pura.
- **Presenter** `settings()` + factory opcional `settings_query_factory`; view
  model `settings_table` (reusa `alert_event_es`/`alert_severity_es`, + `settings_scope_es`).
- **Registro**: `inventory_settings` → `SettingsPage`. **21 páginas reales; 0
  placeholders** — el sidebar canónico (§54) queda 100% con páginas DS reales.
- Guardrail del shell: `test_unbuilt_sections_use_placeholder` se reemplaza por
  `test_every_section_has_a_real_page_no_placeholder` (verifica en el registro que
  las 21 secciones tienen página real y que `PlaceholderPage` no está mapeado).
- **Evidencia**: `test_settings_view_model` (regla de stock bajo, ámbito/severidad
  es-MX, throttle), `test_settings_empty`,
  `test_configuracion_wires_the_real_settings_page` + suites UI = 70 passed;
  inventario `2 failed / 564 passed` (2 pre-existentes, cero regresiones);
  arquitectura `22 failed / 427 passed` desde la raíz del repo (sin fallas nuevas).

**P1-C cerrado:** las 21 secciones canónicas del inventario (§54) son páginas
enterprise del Design System (PageHeader + StandardTable, es-MX, sólo lectura vía
query services, fail-closed) montadas en el shell de navegación lateral; se retira
el último `PlaceholderPage`. Quedan pendientes de fase posterior las acciones de
escritura desde estas páginas (hoy delegadas a los módulos/flujos dedicados).

### Slice 20 — Filtros DS en feeds: KPIBar + filtro de severidad en "Alertas"

Primer enriquecimiento DS sobre las páginas de lectura de alto volumen (patrón
reutilizable para Movimientos/Recepciones/Auditoría en slices siguientes). No hay
componente `FilterBar` en el DS; se usa `SearchInput` (filtro por severidad) +
`KPIBar` (resumen), ambos canónicos. Sólo lectura.

- **`AlertQueryService.list_recent`**: nuevo parámetro opcional `severity` (match
  exacto sobre `severity`), combinable con `branch_id`. Sigue siendo `SELECT`.
- **Presenter**: `alerts(branch_id, severity=None)` propaga el filtro; nuevo
  `alert_kpis(branch_id)` → `KpiViewModel` (Total, Críticas, Advertencias,
  Informativas) contando el feed de la sucursal.
- **View models**: `alert_severity_variant` (INFO→info, WARNING→warning,
  CRITICAL→danger) y `severity_filter_code` (normaliza término libre es-MX/inglés/
  acentos → código; vacío o no reconocido → None = todas).
- **`AlertsPage`**: `KPIBar` (arriba) + `SearchInput`
  ("crítica/advertencia/informativa") que filtra el feed; sin combos ni QSS local.
- **Evidencia**: `test_alerts_severity_filter`, `test_alert_kpis` (presenter),
  `test_severity_filter_code_normalization`, `test_alert_severity_variant`
  (unit) + suites UI = 74 passed; inventario `2 failed / 568 passed` (2
  pre-existentes, cero regresiones); arquitectura `22 failed / 427 passed` desde la
  raíz del repo (sin fallas nuevas).

## P2 — Retiro de bridges legacy de inventario

Objetivo: eliminar los handlers legacy que escribían tablas legacy (`lotes`,
`movimientos_lote`, `movimientos_inventario`) una vez que la ruta canónica los
cubre, sin perder lógica de negocio (PRIORIDAD 0). Se hace por slices, verificando
cobertura canónica antes de borrar.

### Auditoría P2 — inventario de superficies legacy

Bridges/handlers en `backend/application/event_handlers/inventory/`:

| Handler legacy | Escribe | Reemplazo canónico | Cableado (wiring) | Estado |
|---|---|---|---|---|
| `sale_items` (legacy `SaleInventoryHandler`) | engine legacy | `CanonicalSaleInventoryHandler` (`sale_items_bridge`) | ✅ canónico | ya reemplazado (INV-27) |
| `production` (legacy) | engine legacy | `CanonicalProductionInventoryHandler` (`production_items_bridge`) | ✅ canónico | ya reemplazado (INV-27) |
| `purchase_recipe_explosion_handler` | `movimientos_inventario` 'salida' | `CanonicalPurchaseRecipeExplosionHandler` (`purchase_recipe_explosion_bridge`) | ✅ canónico | **retirado (Slice 1)** |
| `purchase_lot_entry_handler` | `lotes` / `movimientos_lote` | `CanonicalPurchaseStockEntryHandler` (hereda `PurchaseReceiptHandler._ensure_lot`) → `inventory_lots` | ✅ canónico (creación de lote viva, Slice 2) | **retirado (Slice 3)** |

### Slice 1 — Retiro de `PurchaseRecipeExplosionHandler` legacy — HECHO

- **Cobertura canónica verificada**: el bridge `CanonicalPurchaseRecipeExplosionHandler`
  está cableado en `core/events/wiring.py` (consume `PURCHASE_STOCK_ENTRY_REGISTERED`,
  postea `ADJUSTMENT_OUT` canónico por componente, idempotente por evento). El flip
  test `test_purchase_recipe_explosion_flip.py` cubre paridad con el legacy: consumo
  de componentes, sin-receta = no-op, idempotencia.
- **Eliminado**: `purchase_recipe_explosion_handler.py` (legacy, sólo lo importaba su
  propio test) + `test_purchase_recipe_explosion_handler.py` (redundante con el flip).
- **Guardrail** `test_inventory_legacy_recipe_handler_retired.py`: el archivo legacy
  no existe, nada lo importa, y el bridge canónico es el handler cableado.
- **Evidencia**: guardrail (3) + flip (3) = 6 passed; inventario
  `2 failed / 565 passed` (2 pre-existentes `legacy_reader_repoints`, cero
  regresiones; −3 del test legacy retirado); arquitectura `22 failed / 430 passed`
  desde la raíz del repo (+3 del guardrail, sin fallas nuevas).

### Slice 2 — Creación de lote canónica en la compra viva — HECHO

Habilitador para retirar `purchase_lot_entry_handler`: el evento vivo
`PURCHASE_STOCK_ENTRY_REGISTERED` trae por línea `inventory_unit`/`expiration`/`lot`
(no `lot_code`), así que el handler canónico nunca creaba lote. Descubrimiento: el
`CanonicalPurchaseStockEntryHandler` **sí** está cableado (prioridad 100) y hereda
`PurchaseReceiptHandler._ensure_lot` — sólo faltaba el mapeo de campos.

- **`CanonicalPurchaseStockEntryHandler`**: porta la regla legacy `_is_lot_tracked`
  (unidad de peso KG **o** `expiration`/`lot`) y deriva `lot_code` por línea
  rastreable — el `lot` explícito si existe, si no `{document}-P{product_id}`
  determinista. Así `_ensure_lot` crea el `inventory_lots` canónico. Idempotente por
  código determinista + `operation_id`.
- Sin tocar semántica de cantidad/peso ni escribir tablas legacy; sólo se cierra la
  brecha de creación de lote (paridad con el legacy, PRIORIDAD 0).
- **Evidencia**: `test_weight_tracked_line_creates_deterministic_canonical_lot`,
  `test_explicit_lot_field_maps_to_canonical_lot_code`,
  `test_non_tracked_line_creates_no_lot`,
  `test_weight_tracked_lot_creation_is_idempotent` (+ 4 existentes) = 8 passed;
  inventario `2 failed / 569 passed` (2 pre-existentes, cero regresiones);
  arquitectura `22 failed / 430 passed` desde la raíz del repo (sin fallas nuevas).

### Slice 3 — Retiro de `purchase_lot_entry_handler` legacy — HECHO

- **Eliminado**: `purchase_lot_entry_handler.py` + `test_purchase_lot_entry_handler.py`.
- **`test_pipeline_end_to_end`** desacoplado de la tabla legacy `lotes`: ahora afirma
  el lote **canónico** (`inventory_lots`, `origin_type='PURCHASE'`) creado por la
  tubería viva completa (direct-purchase → outbox → dispatch →
  `CanonicalPurchaseStockEntryHandler`).
- **Defecto pre-existente corregido**: el evento vivo `PURCHASE_STOCK_ENTRY_REGISTERED`
  no propagaba el actor, así que el `resolve_ingress` fail-closed (P1-A) **descartaba
  silenciosamente** toda recepción de compra canónica (stock comprado nunca aterrizaba).
  `on_receipt_completed` ahora incluye `user_id` (del `actor_user_id` del evento
  fuente). Esto revive las 2 pruebas e2e de la tubería (antes en rojo) y valida la
  creación de lote de Slice 2 extremo a extremo.
- **Guardrail** `test_inventory_legacy_lot_writes_retired.py`: el handler legacy no
  existe, nada lo importa, y ningún handler de inventario escribe `lotes`/
  `movimientos_lote`/`movimientos_inventario`.
- **Evidencia**: guardrail (3) + `test_pipeline_end_to_end` (2, ahora verdes) +
  `test_purchase_stock_entry_flip` (8) = 13 passed; inventario `2 failed / 564 passed`
  (2 pre-existentes, cero regresiones); arquitectura `22 failed / 433 passed` desde la
  raíz del repo (+3 del guardrail, sin fallas nuevas). Las 6 fallas UI de procurement
  (`test_direct_purchase_ui`/`test_enterprise_ui`) son pre-existentes e idénticas
  con/sin este cambio.

### Slice 4 — DROP diferido: readiness (BLOQUEADO) + protección del mecanismo

**Estado: el DROP NO se ejecuta.** La migración diferida ya existe
(`migrations/deferred/legacy_inventory_drop.py`): env-guarded
(`INVENTORY_ALLOW_LEGACY_DROP=1`), **no** registrada en `engine.py` (nunca corre
sola) y ya cubre las tres tablas (+ el resto del mapa de consolidación legacy).
Ejecutarla ahora violaría PRIORIDAD 0: **quedan consumidores vivos** que leen/escriben
estas tablas. Auditoría (no-test, no-migration, no-script):

| Tabla | Consumidores vivos | Repunte objetivo |
|---|---|---|
| `lotes` | `core/services/lote_service.py` (cárnico/FIFO: INSERT/UPDATE/SELECT), `actionable_forecast.py`, `production_query_service.py`, `reporte_email_service.py`, `ui/dashboard.py` | `inventory_lots` (LotQueryService / RegisterInventoryLotUseCase) |
| `movimientos_lote` | `core/services/lote_service.py` (INSERT) | `inventory_ledger` + `inventory_lots` (trazabilidad canónica) |
| `movimientos_inventario` | `repositories/inventory_repository.py`, `backend/application/queries/inventory_balance_service.py`, `api/routers/inventario.py`, `core/delivery/infrastructure/inventory_reservation_adapter.py`, `core/services/inventory/unified_inventory_service.py`, `core/services/recipe_engine.py`, `core/services/analytics/analytics_engine.py`, ~~`repositories/productos.py`~~ (repuntado, Slice 5) | `inventory_ledger`/`inventory_ledger_lines` + `InventoryAvailabilityQueryService` |

Scripts (`scripts/reconcile_inventory.py`, `scripts/seed_demo.py`) también las usan
pero son herramientas fuera del runtime — se repuntan al final.

- **Guardrail** `test_legacy_inventory_drop_is_parked_and_guarded.py`: la migración
  existe, **no** está en `engine.py`, está env-guarded (`!= "1"` → `RuntimeError`) y
  cubre las tres tablas. Protege el mecanismo de seguridad (nadie la registra ni la
  desprotege por accidente) hasta que los consumidores lleguen a cero.
- **Evidencia**: guardrail 4 passed; sin cambios de runtime (no se dropea nada; no
  se registra migración); inventario/arquitectura sin fallas nuevas.

### Slice 5 — Repunte `productos.has_movements` al ledger canónico — HECHO

Primer repunte de lector concreto hacia el DROP: `ProductoRepository.has_movements`
(sonda de "¿el producto tiene movimientos?" para la guarda de borrado) consultaba
`movimientos_inventario` legacy; ahora consulta `inventory_ledger_lines` canónico.
Era la **única** referencia a tabla legacy de inventario en `repositories/productos.py`,
así que ese archivo sale del set de consumidores. Método sin llamadores hoy → cero
riesgo de runtime; el repunte deja la semántica correcta post-cutover.

- **Evidencia**: `test_productos_has_movements_canonical` (2) passed; inventario
  `2 failed / 566 passed` (2 pre-existentes, cero regresiones); ratchet de productos
  legacy intacto (`repositories/productos.py` sigue leyendo la tabla `productos`, no
  la de inventario).

### Slice 6 — Retiro de `repositories/inventory_repository.py` (legacy, IDs int) — HECHO

Segundo repunte hacia el DROP. Al investigar `repositories/inventory_repository.py`
(el `InventoryRepository` legacy de nivel superior — IDs `int`, escribía
`movimientos_inventario`/`inventario_actual`/`branch_inventory`) se confirmó que:

- **Cero importadores de producción.** `core/app_container.py` y todo caller real
  usan el módulo canónico-adyacente `backend.infrastructure.db.repositories.
  inventory_repository` (archivo distinto, mismo nombre corto) — ya protegido por
  `test_app_container_inventory_canonical_route.py`.
- El shim `InventoryService` (`core/services/inventory_service.py`, INV-27)
  **ignora por completo** el parámetro `inventory_repo`: siempre delega en
  `CanonicalInventoryRepository` (ledger). El `InventoryRepository` legacy que
  recibía era letra muerta incluso donde se construía.
- Sólo dos *fixtures* de test lo construían (`tests/conftest.py::sales_svc`,
  `tests/test_sales_customer_loyalty.py::sales_svc_checkout`) — uno de ellos
  incluso lo pasaba en la posición equivocada (bug preexistente de fixture, fuera
  de alcance; **no se tocó** esa semántica: se comprobó bit a bit que el conjunto
  de tests que fallan antes/después es idéntico).

**Cambios:**
- Eliminado `repositories/inventory_repository.py`.
- Ambas fixtures ya no importan/construyen el repo legacy; `InventoryService(...)`
  se llama con la firma real del shim (sólo la conexión).
- **Ratchet de `productos` actualizado**: se quita `repositories/inventory_repository.py`
  de la allowlist (el archivo también hacía `UPDATE productos`; al desaparecer, deja
  de ser consumidor de esa tabla también).
- **Guardrail** `test_legacy_top_level_inventory_repository_retired.py`: el archivo
  no existe, ningún import real lo referencia (se excluyen coincidencias dentro de
  literales de otros guardrails), y `app_container.py` usa sólo el módulo canónico.
- **Evidencia**: guardrail (3) + ratchet (2) + `test_app_container_inventory_canonical_route`
  (2) = 7 passed; `tests/test_sales.py` + `tests/test_sales_customer_loyalty.py`
  → mismo conjunto de fallas antes/después (diff vacío, cero regresión, cero
  arreglo colateral de bugs preexistentes); `tests/unit/` → mismo conjunto de
  fallas antes/después (diff vacío); inventario `2 failed / 566 passed` (2
  pre-existentes); arquitectura `22 failed / 440 passed` desde la raíz del repo
  (+3 del guardrail, sin fallas nuevas).

### Slice 7 — Repunte del chequeo de idempotencia del adaptador de delivery — HECHO

Tercer repunte hacia el DROP. `ReservationServiceInventoryAdapter.commit_for_order`
(delivery) ya posteaba la deducción de stock vía `InventoryService.deduct_stock`
(shim canónico INV-27) — esa parte ya era correcta. Pero su chequeo de
idempotencia previo (`_movement_exists`) seguía consultando la tabla legacy
`movimientos_inventario`, que el shim **ya no escribe** — así que el chequeo
siempre devolvía `False` (letra muerta: nunca detectaba un reintento ya
procesado). El ledger canónico ya es idempotente por `operation_id` (una repetición
no duplica el movimiento), pero el adaptador no podía distinguir "recién
comprometido" de "ya comprometido" para sus contadores `committed`/`skipped`.

- **`_movement_exists`** ahora consulta `inventory_ledger` con la clave
  `{operation_id}:DECREASE` — el sufijo interno que `CanonicalInventoryRepository`
  usa para namespacing de `decrease_stock` (única operación que este adaptador
  ejecuta). Acoplamiento intencional y documentado: si ese sufijo cambia, el
  chequeo debe romperse ruidosamente, no volver a fallar en silencio (`False`
  constante).
- **Auditoría de regresión**: `tests/test_delivery_inventory_projection.py` (4
  tests) y `tests/test_delivery_phase12_required.py` (5 de 7 tests) ya fallaban en
  el commit padre por motivos no relacionados (tabla `inventory_reservations`
  faltante; `int(event["id"])` sobre un UUID) — confirmado diffeando el conjunto
  exacto de fallas antes/después (idéntico).
- **Evidencia**: `test_delivery_movement_exists_canonical.py` (3, nuevo — valida
  contra el flujo real `InventoryService.deduct_stock`, no SQL arbitrario) = 3
  passed; inventario `2 failed / 569 passed` (2 pre-existentes, cero regresiones);
  arquitectura `29 failed / 534 passed` desde la raíz del repo (línea base sin
  cambios tras el merge externo de merma/caja+compras; ninguna de las 29 toca este
  cambio).

### Slice 8 — Repunte de `AnalyticsEngine.inventory_intelligence.top_consumed` — HECHO

Cuarto repunte hacia el DROP. `top_consumed` (métrica BI "productos más consumidos
en 30 días") consultaba `movimientos_inventario` (`tipo='SALIDA'`). Auditoría: el
método tiene **cero llamadores** en todo el repositorio (incl. tests) — pero la
clase `AnalyticsEngine` sí está viva (`core/app_container.py`,
`modulos/reportes_bi_v2.py`, wired a eventos), así que se repuntó la query en vez
de eliminar el método público (cambio más chico, preserva el contrato de una
clase activa).

- La query ahora suma `inventory_ledger_lines.quantity` uniendo `inventory_ledger`,
  filtrando por los tipos canónicos con dirección `DECREASE` (§ `MOVEMENT_DIRECTION`):
  `SALE_ISSUE`, `TRANSFER_DISPATCH`, `PRODUCTION_CONSUMPTION`,
  `SLAUGHTER_INPUT_FUTURE`, `ADJUSTMENT_OUT`, `WASTE`, `SHRINKAGE`,
  `EXPIRY_DISPOSAL`, `SUPPLIER_RETURN` — el equivalente canónico exacto de
  "SALIDA" — acotado por `branch_id` y los últimos 30 días de `occurred_at`.
  El bloque `low_stock` (que sí lee `productos`, ajeno a esta slice) no se tocó.
- **Evidencia**: `test_analytics_top_consumed_canonical.py` (2, nuevo — prueba
  contra el flujo real `PostInventoryMovementUseCase`, confirma que una
  `PURCHASE_RECEIPT` [INCREASE] no cuenta y que el alcance por sucursal es
  correcto); `tests/test_bi_rentabilidad_franchise_bugs.py` +
  `tests/test_analytics_profitability_fallback.py` + `tests/test_new_services.py`
  → mismo conjunto de fallas antes/después (diff vacío, las 4 de
  `test_new_services.py` son pre-existentes y ajenas); ratchet de `productos`
  intacto (`analytics_engine.py` sigue en la allowlist por su lectura de
  `productos`, no tocada); inventario `2 failed / 571 passed` (2 pre-existentes,
  cero regresiones); arquitectura `29 failed / 534 passed` desde la raíz del repo
  (línea base sin cambios).

### Slice 9 — Retiro del insert de auditoría legacy en `recipe_engine` — HECHO

Quinto repunte hacia el DROP. Se evaluaron dos candidatos: el endpoint REST
`api/routers/inventario.py` (`/movimientos/{producto_id}`) y el insert de
auditoría de `core/services/recipe_engine.py`. El primero quedó descartado para
esta slice: su única cobertura (`tests/test_fase_g_api_gateway.py`) falla en
la totalidad de sus 28 casos en el setup de fixtures por
`ModuleNotFoundError: No module named 'fastapi'` — una limitación de entorno
preexistente y ajena a este trabajo — por lo que no puede verificarse
localmente; queda pendiente para cuando el entorno tenga `fastapi` instalado.

`RecipeEngine._registrar_movimiento_legacy_audit_only` insertaba en
`movimientos_inventario` tras cada corrida de producción. Su propio docstring
("FIX FALLA-7") ya documentaba que era puramente informativo: **nunca
actualizó existencia** — eso lo hace el paso 6 de `ejecutar_produccion`
(bus `PRODUCTION_ITEMS_PROCESS` → `CanonicalProductionInventoryHandler`, que
postea al ledger canónico). Además, el mismo loop del paso 6b ya inserta en
`produccion_detalle` con el detalle exacto de cada movimiento (producto,
cantidad, unidad, rendimiento, tipo) — el insert legacy era estrictamente
redundante con datos ya cubiertos por dos fuentes canónicas. Confirmado sin
lectores: ningún módulo de producción consulta `movimientos_inventario`
filtrando por `referencia_tipo='PRODUCCION'`; los tests que crean esa tabla en
sus fixtures de `recipe_engine` (`test_recipe_engine_costing_phase6.py`,
`test_recipe_components_quantities_phase4.py`,
`test_recipe_engine_tipo_receta_normalization.py`,
`test_recipe_engine_uuid_identity.py`, `test_traceability_phase9.py`,
`test_bloque1_p0_fixes.py`) nunca aseveran su contenido — la crean solo de
forma defensiva (el insert estaba envuelto en `try/except` que ya lo hacía
"no crítico" si la tabla faltaba). Se eliminó el método y su única llamada;
se actualizó el comentario de cabecera del archivo.

- **Evidencia**: `tests/integration/test_recipe_engine_uuid_identity.py` +
  `tests/test_traceability_phase9.py` + `tests/test_flujo_completo.py` +
  `tests/test_bloque1_p0_fixes.py` + `tests/test_recipe_components_quantities_phase4.py`
  + `tests/test_recipe_engine_tipo_receta_normalization.py` +
  `tests/test_recipe_engine_costing_phase6.py` → mismo resultado antes/después
  (`3 failed, 53 passed, 12 errors`, todas preexistentes y ajenas —
  `sync_outbox`/`ProcesarVentaUC` deprecado/etc.); inventario
  `2 failed / 571 passed` (2 pre-existentes, cero regresiones); arquitectura
  `29 failed / 534 passed` desde la raíz del repo (línea base sin cambios).

### Slice 10 — Repunte de `production_query_service.get_active_lotes_count` — HECHO

Sexto repunte hacia el DROP, primer consumidor de la tabla legacy `lotes`
(distinta de `movimientos_inventario`). Auditoría de los 6 archivos que leen
`lotes` directamente (`lote_service.py` [el más grande, FIFO cárnico —
pendiente, ítem 1 abajo], `ui/dashboard.py`, `actionable_forecast.py`,
`reporte_email_service.py`, `seed_demo.py`, `production_query_service.py`):
se eligió `production_query_service.py` por ser el más chico y acotado —
un `SELECT COUNT(*) FROM lotes WHERE estado='activo'`, usado por el KPI
"lotes activos" del dashboard de Producción (`get_daily_kpis` +
`get_active_lotes_count`, ambos wireados en vivo vía `core/app_container.py`
y llamados directo por `modulos/produccion.py:227`).

- El equivalente canónico de `estado='activo'` (que en la tabla legacy
  implicaba además `peso_actual_kg>0`, ver `lote_service.py`) es: un lote con
  saldo restante en `inventory_balances` — `COUNT(DISTINCT lot_id)` con
  `quantity>0 OR weight>0`. Se extrajo a un helper `_count_active_lots(db)`
  compartido por ambas funciones públicas (antes duplicaban la misma query).
- **Evidencia**: `tests/test_production_query_service.py` (fixtures migradas de
  `CREATE TABLE lotes` a `CREATE TABLE inventory_balances`; se agregó
  `test_same_lot_split_across_locations_counts_once` para cubrir el `DISTINCT`)
  + `tests/test_bloque2_query_service.py` → `62 passed` (línea base `61
  passed`, +1 test nuevo, cero regresiones); `tests/test_recipe_events.py` +
  `tests/integration/test_meat_production_use_case.py` +
  `tests/architecture/test_remediacion0_guardrails.py` → `24 passed` sin
  cambios; inventario `2 failed / 571 passed` (2 pre-existentes); arquitectura
  `29 failed / 534 passed` desde la raíz del repo (línea base sin cambios).

### Slice 11 — Repunte de `reporte_email_service` ("Lotes por vencer") — HECHO

Séptimo repunte hacia el DROP, segundo lector de `lotes` retirado. El reporte
diario por email contaba `SELECT COUNT(*) FROM lotes WHERE
DATE(fecha_caducidad)<=? AND estado='activo'`. Se repuntó a
`ExpiryQueryService.list_at_risk()` (INV-7, `backend/application/inventory/
queries/expiry_query_service.py`) — la misma lectura canónica que ya usa la
página de alertas/cadena de frío del módulo Inventario — sobre
`inventory_balances` ⋈ `inventory_lots`, filtrando por clasificación
EXPIRED/CRITICAL/WARNING de `ExpiryRiskService`.

- **Cambio de semántica documentado (no regresión, mejora deliberada)**: la
  query legacy solo contaba lotes con `fecha_caducidad<=hoy` (vencidos o que
  vencen hoy). El canónico `list_at_risk()` también incluye WARNING (≤7 días,
  configurable) y CRITICAL (≤2 días) — la misma definición de "at risk" que ya
  ve el usuario en el módulo Inventario. Se prefirió una sola definición de
  "lote en riesgo" en todo el sistema en vez de preservar el corte exacto de
  la query legacy retirada.
- Justo al lado, en el mismo método, `stock_bajo` ya usaba
  `InventoryStockAggregateQueryService` canónico — se siguió el mismo patrón
  (import inline + try/except a 0) para consistencia dentro del archivo.
- **Evidencia**: `tests/integration/inventory/test_reporte_email_lotes_canonical.py`
  (2, nuevo — sin cobertura previa de `_build_reporte_diario`; siembra lotes
  EXPIRED/CRITICAL/OK vía el flujo real de esquema canónico y confirma el
  conteo en el HTML generado); `tests/test_uuid_only_guard_rails.py` sin
  cambios (9 passed); inventario `2 failed / 573 passed` (2 pre-existentes,
  +2 tests nuevos); arquitectura `29 failed / 534 passed` desde la raíz del
  repo (línea base sin cambios).

### Pendiente P2 (orden de repunte antes del DROP)

1. **`lote_service` cárnico/FIFO** → migrar lotes/movimientos_lote a `inventory_lots`
   + ledger (es el mayor consumidor y el de mayor lógica de negocio).
2. **Lectores restantes de `lotes`**: `ui/dashboard.py`, `actionable_forecast.py`
   (repuntar a `inventory_lots`/`inventory_balances`, mismo patrón de
   `ExpiryQueryService`); `seed_demo.py` (repuntar la creación de lotes demo a
   `inventory_lots`).
3. **`movimientos_inventario`**: repuntar lectores/escritores restantes
   (`inventory_balance_service` [reconciliación legacy↔legacy],
   `unified_inventory_service`, `api/routers/inventario` [bloqueado por falta
   de `fastapi` en este entorno]) al ledger canónico.
4. **Herramientas/scripts** (`reconcile_inventory`) — su propósito es
   reconciliar tablas legacy entre sí; probablemente se retira junto con el
   DROP en vez de repuntarse.
5. Recién con paridad de `InventoryReconciliationService` y cero consumidores,
   ejecutar la migración diferida con `INVENTORY_ALLOW_LEGACY_DROP=1`.
