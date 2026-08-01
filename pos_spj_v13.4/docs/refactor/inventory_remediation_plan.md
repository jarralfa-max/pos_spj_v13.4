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

### Pendiente P0-A (próximos slices)

- **§5.2 composition root** `InventoryUseCaseFactory` con checker/SessionContext/
  scope resolver reales; UI/handlers dejan de instanciar con constructores vacíos
  (esto cierra el residuo: hoy el default de pruebas es permisivo si producción no
  inyecta checker).
- **§5.3 `InventoryExecutionContext`** + aplicar `InventoryScopePolicy` en todos
  los commands/queries.
- **§5.4** eliminar fallbacks ficticios (`"desktop"`, `"system"`, `"1"`, `"MAIN"`,
  `warehouse_id = branch_id`, `location_id = warehouse_id`).
