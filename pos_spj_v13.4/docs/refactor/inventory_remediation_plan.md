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
- Transferencias (agregado propio — se abordará junto con P1-B transferencias
  físicas).
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
(`RegisterWasteUseCase` / transferencias INV-12), sin sobre de evento externo.
Pendiente: bridges legacy → P2.

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
