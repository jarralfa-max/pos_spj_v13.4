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

### Pendiente P0-B

- §6.3 `RebuildInventoryBalancesUseCase` / `ValidateInventoryProjectionUseCase`
  (reconstrucción desde ledger + detección de drift).
- §7 Foreign Keys + CHECK + índices + unicidad de operation_id/event_id +
  `PRAGMA foreign_key_check`/`integrity_check` limpios.
- §4.1 `validate_uuidv7`/`new_uuidv7` + pruebas de versión real de UUID.
- §4.3 unidades canónicas (`unit_id` UUID, no texto libre) en líneas del ledger.
- §8 ubicaciones técnicas reales (no `warehouse_id` como ubicación).
