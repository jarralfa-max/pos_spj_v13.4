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

### Pendiente P0-A (próximos slices)

- **§5.3 `InventoryExecutionContext`** + aplicar `InventoryScopePolicy` en todos
  los commands/queries (sucursal activa, almacenes autorizados, pertenencia).
- **§5.4 (resto)** eliminar fallbacks `warehouse_id = branch_id`,
  `location_id = warehouse_id`, `"system"`/`"MAIN"` donde persistan; cuenta técnica
  `service_account_id` para procesos automáticos.
