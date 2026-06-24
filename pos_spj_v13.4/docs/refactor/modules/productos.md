# Módulo PRODUCTOS — auditoría F7

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

### Pendiente

4. **F2 identidad:** `int(producto_id)` (5) restantes en UI → pasar UUID str directo.
   Riesgo: DB aún con ids int; ligado al corte UUID.
5. **F3 transacción:** `product_catalog_service` (5 commit/5 rollback) → repo + `ConnectionUnitOfWork`;
   y los 2 `commit()` restantes en `productos.py` (frontera de tx import/branch-product) → UoW.

### Pre-existente (no de este refactor)

10 tests rojos en `production_cost_service` / `production_query_service` /
`product_catalog_refactor`: esperan `int`, el código ya devuelve `str` UUID
(`assert '3' == 3`). Alinear a UUID pendiente.

## Residuales / notas

- `int_str_contract` también en `sales_application_service.py` (1) — fuera de scope PRODUCTOS.
- Sin tests de comportamiento de productos aún; crear antes de extraer SQL de UI (regla 4).
