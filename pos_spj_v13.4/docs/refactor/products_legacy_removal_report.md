# PROD-19 — Reporte de remoción de legacy de Productos

Estado del **corte atómico** del maestro de Productos (aprobado por el usuario:
"Corte atómico completo"). Se ejecuta de forma **incremental con verificación de
cero regresiones** en cada paso (mismo método que el corte de Inventario), para no
romper el POS/Inventario/Compras vivos mientras se repuntan los 78 consumidores.

## Alcance del legacy a eliminar (ver `products_legacy_inventory.md`)

- **Maestro**: tabla `productos` (existencia/precio float, categoria/unidad texto,
  `sucursal_id`, flags `es_*`) + `branch_products` (precio_local).
- **Recetas** (8 tablas paralelas): `recetas`, `receta_componentes`,
  `product_recipes`, `product_recipe_components`, `product_recipes_abarrotes`,
  `componentes_producto`, `paquetes_componentes`, `recipe_dependency_graph`
  + motores `core/services/recipe_engine.py`, `core/services/recipes/*`,
  `repositories/recetas.py`.
- **Rendimientos** solo-pollo: `rendimiento_pollo`, `rendimiento_derivados`,
  `meat_production_yields`, `production_yield_analysis`.
- **UI**: `modulos/productos.py` (1534 líneas), `modulos/dialogs/receta_dialog.py`,
  `modulos/spj_product_search.py`.
- **Permisos** gruesos (`PRODUCTOS`, `CREAR_PRODUCTO`) y **eventos** español
  (`PRODUCTO_CREADO`, `RECETA_CREADA`).

## Acoplamiento medido (bloquea el DROP)

- **78** archivos con SQL directo sobre `productos` (FROM/INTO/UPDATE/JOIN).
- **10** migraciones con `FOREIGN KEY REFERENCES productos`.
- El app vivo monta `modulos/productos.py` desde `core/ui/module_loader.py` e
  `interfaz/main_window.py`.

## Pasos del corte

| Paso | Descripción | Estado |
| ---- | ----------- | ------ |
| 1 | **Backfill** `productos` → `products` canónico (migración 148, aditiva, idempotente, sin precio/existencia; ids UUID preservados) | ✅ |
| 2 | Scaffolding: DROP diferido `migrations/deferred/legacy_products_drop.py` (env-guard `PRODUCTS_ALLOW_LEGACY_DROP=1`, **no registrado**), este reporte | ✅ |
| 3 | Repuntar lecturas de catálogo/búsqueda de POS/Ventas a `products` (o vista de compat) | ⏳ |
| 4 | Migrar recetas legacy → `recipe`/`recipe_version` canónico; neutralizar `recipe_engine`/`core/services/recipes` | ⏳ |
| 5 | Migrar rendimientos `rendimiento_pollo` → `yield_profile*` | ⏳ |
| 6 | Repuntar compras/producción/BI/fidelidad/forecast a `products.id` | ⏳ |
| 7 | Borrar `modulos/productos.py` + cablear UI enterprise (`ModuloProductosEnterprise`) en `module_loader`/`main_window` | ⏳ |
| 8 | Migrar permisos `PRODUCTOS`→`PRODUCTS_*` y eventos `PRODUCTO_*`→`PRODUCT_*` | ⏳ |
| 9 | Allowlist → vacía; guardrails `test_no_legacy_products_imports` / `test_products_legacy_allowlist_is_empty` | ⏳ |
| 10 | **DROP** destructivo (`PRODUCTS_ALLOW_LEGACY_DROP=1`) de ~20 tablas legacy + trigger | ⏳ |

## Invariante de no-regresión

Cada paso mide node-ids de tests antes/después (0 fallas nuevas) y bootstrap
limpio, como en INV-27/INV-28. El DROP (paso 10) es irreversible y sólo se ejecuta
tras confirmar cero consumidores legacy.

## Métricas (se completan al cerrar el corte)

- Allowlist inicial: (los 78 consumidores + UI legacy) — pendiente de enumerar.
- Allowlist final: **vacía** (objetivo).
- Tablas consolidadas: `productos`+`branch_products` → `products`+`branch_product`;
  8 recetas → `recipe*`; 4 rendimientos → `yield_profile*`.
- Bootstrap limpio: ✅ (148 migraciones, cobertura 80.0%).
