# Módulo PRODUCTOS — auditoría F7

## Estado: IMPLEMENTATION (REGLA CERO resuelta) — 2026-06-25

> El baseline F0 de abajo quedó **OBSOLETO**: la UI ya fue refactorizada.
> Reauditoría 2026-06-25 sobre el código actual:
> - `modulos/productos.py`: **0** SQL crudo, **0** `commit`, **0** `int(_id)`,
>   **0** default-`1`. Delega a use cases / `product_catalog_service` y lee por
>   `product_query_service`. ✅
> - `product_catalog_service` y backend `product_repository`: UUIDv7-native
>   (`new_uuid()`, id explícito). ✅
> - `product_query_service`: sin `int|str`, sin `lastrowid` (solo `index/limit:int`
>   legítimos). ✅
> - **Corregido en esta fase:** `repositories/productos.py.create()` (legacy de
>   lectura en vivo) acuñaba con `lastrowid` → `new_uuid()`; `_write_audit` logs
>   sin id → con id; hints `int`→`str`. `compras_pro.py` import roto
>   `ProductosRepository` + `int(pid)` → `ProductoRepository`/`str(pid)`.
> - Tests: `tests/integration/test_productos_repo_uuid_identity.py` (2).
> - Pendiente menor: `unidad` hardcodeada en UI → `ModuleSettingsService`
>   (regla 24); métodos de escritura muertos en el repo legacy (dup inofensiva).
>
> ---
> _Baseline histórico (obsoleto), conservado para trazabilidad:_

## Estado: F0 (baseline congelado)

A diferencia de MERMA, PRODUCTOS sigue siendo legacy pesado. La UI PyQt ejecuta
SQL crudo + `commit()`, castea identidades con `int(...)`, usa default arbitrario
de sucursal `1`, y un "application service" hace commit directo.

## Baseline de violaciones (medido 2026-06)

| Archivo | Violaciones |
|---|---|
| `modulos/productos.py` | 11 SQL execute, 2 commit, 8 SELECT, 2 INSERT, 2 UPDATE, 6 `int(_id)`, 5 `uuid4`, 2 default-1 |
| `backend/application/queries/product_query_service.py` | 10 SELECT, 3 `int \| str` |
| `backend/application/services/product_catalog_service.py` | 5 commit, 5 rollback, 1 INSERT, 5 UPDATE (service hace SQL+tx directo) |
| `backend/infrastructure/db/repositories/product_repository.py` | 5 `int \| str`, 6 SELECT, 1 INSERT/UPDATE, 1 commit/rollback |

Ratchet: `tests/architecture/test_productos_guardrails.py` — cada número solo baja.

## Plan F7 (orden por riesgo)

1. ✅ **F1 contratos** — `product_id: int | str` → `str` en `product_repository` (5) +
   `product_query_service` (4, incl. un `int` suelto). Verificado: sin casts `int(product_id)`. (`2053c1e`)
2. ✅ **F1 default sucursal** — `productos.py` `sucursal_id=1` y `getattr(...,'sucursal_id',1)`
   → fuente de sesión, sin literal. (`a2aeb72`)
3. ✅ **uuid4 → `new_uuid()`** — era alias `new_uuid as uuid4` (ya UUIDv7); renombrado. (`cba5dc1`)

### F5 SQL en UI — en curso

Cluster **branch-products + historial de precios** extraído test-first a
`backend/infrastructure/db/repositories/branch_product_repository.py` (PyQt-free)
y cubierto por `tests/unit/test_branch_product_repository.py` (9 tests, corren sin
Qt). La UI (`_cargar_sucursales_combo_bp`, `_cargar_tabla_branch_products`,
`_guardar_branch_product`, `_ver_historial_precio`) ahora delega y solo arma widgets.

Segunda tanda: `_importar_excel` (upsert masivo) y el lookup del scanner
extraídos a `ProductRepository` (`find_id_by_barcode_or_code`,
`find_id_by_name_or_code`, `update_basic_fields_from_import`, `insert_from_import`),
cubiertos por `tests/unit/test_product_repository_import.py` (7 tests headless).
`cargar_catalogo` ya delegaba en `ProductQueryService` (sin SQL crudo).

**`modulos/productos.py` ahora tiene CERO SQL** (`.execute`/SELECT/INSERT/UPDATE = 0).
El SQL vive en los repos (su lugar correcto); el baseline del repo subió en
consecuencia (SELECT 6→8, INSERT/UPDATE 1→2).

Nota: los tests de protección de métodos PyQt directos **siempre se saltan aquí**
(PyQt5 no instalado). Por eso la protección se hace en la capa repo (headless).

### F3 transacciones — hecho

`product_catalog_service` (create/update/_set_product_state) ahora usa
`ConnectionUnitOfWork` como frontera de transacción: **cero `commit()`/`rollback()`
literales** en el service (commit en éxito, rollback en error vía context manager).
Los 2 `commit()` de la UI (`_guardar_branch_product`, `_importar_excel`) también
envueltos en `ConnectionUnitOfWork` → **`productos.py` con cero commit/rollback**.

Cubierto por `tests/unit/test_product_catalog_service_uow.py` (4 tests headless:
commit en éxito, rollback en error sin fila parcial).

### F2 identidad — hecho

Eliminados todos los casts de identidad a entero en `productos.py` (UUID-ready):
- `product_id=int(producto_id)` → `str(...)` en deactivate/restore/set_active.
- Comparación componente↔producto en recetas → comparación de strings.
- `_producto_seleccionado_catalogo`: `int(cell.text())` → str directo a `get_product`.
- `DialogoProducto.guardar`: `int(result.entity_id)` → `str(...)`.
- `get_catalog_filter_ids` ahora devuelve `set[str]`; filtro usa `str(r['id']) in ids`.
- Firmas `producto_id: int` → `str` en 4 métodos.

Los `int(...)` restantes en `productos.py` son sobre el flag `activo` (0/1), no identidad.
Cubierto por `tests/test_phase3_query_services.py` (query service) — verde.

### Pendiente

5. **F5 resto del service:** el SQL de `product_catalog_service` (INSERT/UPDATE
   directos en la rama sin repo) podría delegarse del todo a `ProductRepository`.
6. **Corte UUID global (FASE 2.5):** la DB sigue con PK enteras; el runtime ya
   trata identidad como `str`, pero la migración atómica de esquema queda pendiente
   (cierra `legacy_id` / `AUTOINCREMENT` del test de cutover, hoy pre-existentes).

### Pre-existente (no de este refactor)

`test_product_catalog_refactor::test_create_product_use_case_persists_zero_inventory`
falla con `sqlite3.IntegrityError: datatype mismatch` (esquema UUID vs int),
presente antes de estos cambios (verificado con stash).

### Pre-existente (no de este refactor)

10 tests rojos en `production_cost_service` / `production_query_service` /
`product_catalog_refactor`: esperan `int`, el código ya devuelve `str` UUID
(`assert '3' == 3`). Alinear a UUID pendiente.

## Residuales / notas

- `int_str_contract` también en `sales_application_service.py` (1) — fuera de scope PRODUCTOS.
- Sin tests de comportamiento de productos aún; crear antes de extraer SQL de UI (regla 4).
