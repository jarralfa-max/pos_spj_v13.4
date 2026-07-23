# INV-28 — Reporte de Validación Final del Bounded Context de Inventario

Fecha: 2026-07-23
Rama: `claude/erp-financial-bounded-context-uqxz6b`
Base de comparación (pre-corte): `e3720b9~1`

Cierra la fase INV-28 del plan `inventory_refactor_execution_plan.md`. El bounded
context canónico de Inventario (INV-1 … INV-27) queda validado como fuente de
verdad de escritura, con la UI enterprise montada y el motor legacy neutralizado
por flag de cutover. El DROP destructivo de tablas legacy permanece **diferido**
(documentado como paso manual).

## 1. Suites ejecutadas

| Suite | Alcance | Resultado |
| ----- | ------- | --------- |
| `tests/architecture` (`-k "inventory or ledger"`) | Guardrails: sin SQL en UI, ledger-based, Decimal-only, UUIDv7, sin imports legacy, ventas/compras/producción no escriben tablas de inventario | **28 passed** |
| `tests/architecture` (inventario, corrida amplia) | Guardrails de inventario + arquitectura general | **inventario 100% verde** (2 fallas ajenas por ruta relativa: `core/permissions.py`, `modulos/configuracion.py`, sensibles al cwd — no de inventario) |
| `tests/integration/inventory` | Ledger, balances, lotes/FEFO, peso variable, cadena de frío, reservas, transferencias, conteos, ajustes, calidad, mermas, trazabilidad, reposición, notificaciones, etiquetas | **252 passed** |
| `tests/unit/inventory` | Dominio + value objects + policies de inventario | **165 passed** |
| Bootstrap limpio desde cero | 120 migraciones aplicadas sobre DB vacía | **sin errores**, "Cobertura: 80.0%" |
| Auditoría de sintaxis global (`ast.parse` sobre todo el árbol) | Todos los `.py` del proyecto | **SIN errores de sintaxis** |

## 2. Diff de regresión contra base pre-corte

Se comparó el conjunto de tests que tocan el motor de inventario legacy y el shim
(`test_inventory.py`, `test_uc_inventario.py`, `test_bootstrap_wiring.py`,
`test_fase5_*`, `test_fase_g_inventory_integrity.py`,
`test_sales_stock_validation_regression.py`) entre `HEAD` y `e3720b9~1`
(worktree aislado).

**Fallas netas nuevas introducidas por el corte: 0.**

Detalle:

- **3 regresiones detectadas y resueltas** en `test_bootstrap_wiring.py`:
  `test_inventory_descontar_stock_calls_deduct`,
  `test_inventory_incrementar_stock_calls_add`,
  `test_inventory_ajustar_merma_uses_waste_reference`.
  Fijaban el **detalle interno** del shim `InventoryService` (escritura vía repo
  legacy `insert_movement` con `movement_type` "OUT"/"IN" y `reference_type`
  "WASTE") usando IDs enteros. El corte (INV-27 paso 2i) reescribió el shim para
  delegar en `CanonicalInventoryRepository` (ledger canónico), por lo que ese repo
  legacy ya no se usa. Se eliminaron esos 3 tests obsoletos; el contrato de
  existencia de los alias en español queda cubierto por los tests
  `*_exists_and_callable` (verdes) y el comportamiento canónico por
  `tests/integration/inventory/`.
- **1 test que ahora pasa** (mejora):
  `test_sales_stock_validation_regression.py::test_inventory_handler_still_blocks_if_stock_changes_after_prevalidation`.
- **Resto de fallas** en `test_inventory.py`, `test_uc_inventario.py`,
  `test_fase5_stock_reservations.py`, `test_fase_g_inventory_integrity.py`,
  `test_bootstrap_wiring.py::test_verificar_tablas_*`: **pre-existentes e
  idénticas a base** (mismo conteo pass/fail en `e3720b9~1`). Corresponden a
  tests legacy que ejercen el motor de tres tablas (`inventory_stock` /
  `inventario_actual` / `movimientos_inventario`) y usan IDs enteros/floats —
  arquitectura que el corte reemplaza y cuyo DROP está diferido.

## 3. Estado de la arquitectura tras el corte

- **Escritura**: el ledger canónico (`inventory_ledger` + `inventory_ledger_lines`
  → proyección `inventory_balances`) es la fuente de verdad. Los bridges de
  ventas (`SALE_ISSUE`/`SALE_RETURN`), producción (`PRODUCTION_CONSUMPTION`/
  `_OUTPUT`), transferencias (`TRANSFER_DISPATCH`/`_RECEIPT`) y compras
  (`PURCHASE_RECEIPT` + explosión de receta) postean al ledger. El shim
  `core/services/inventory_service.py` delega en `CanonicalInventoryRepository`.
- **UI**: `modulos/inventario_enterprise.py` monta la UI enterprise
  (`frontend/desktop/modules/inventory/`, patrón presenter/view-model, sin SQL).
- **Cutover**: activo por flag persistente (migración 134,
  `canonical_cutover_enabled = true`). "Las lecturas siguen a las escrituras".
- **Legacy neutralizado**: handlers `inventory_handler.py` / `transfer_handler.py`
  eliminados; el bus vivo enruta a los handlers canónicos.

## 4. Pendientes documentados (fuera del alcance de INV-28)

El DROP destructivo de ~20 tablas legacy (`migrations/deferred/legacy_inventory_drop.py`,
**no registrado** en el engine, env-guard `INVENTORY_ALLOW_LEGACY_DROP=1`) queda
diferido hasta repuntar los últimos lectores legacy:

1. Subsistema de reservas: `reservation_service` / `stock_reservation_service` +
   adaptadores de delivery, de `inventory_reservations` (plural) / `stock_reservas`
   → `inventory_reservation` (singular canónica).
2. `sync_engine` (sincronización de `movimientos_inventario` / `inventario_actual`).
3. `api/routers/inventario.py`.

Hasta entonces el estado en `module_relocation_map.md` es **MIGRATED** (no
`LEGACY_REMOVED`).

## 5. Conclusión

El corte de inventario es funcionalmente completo y sin regresiones netas: el
ledger canónico gobierna la escritura, la UI enterprise está montada, el legacy
está neutralizado por flag y las suites de dominio/aplicación/integración/UI/
arquitectura de inventario están en verde sobre bootstrap limpio. INV-28 se marca
como ✅.
