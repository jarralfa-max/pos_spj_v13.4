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
| 4 | **Backfill** recetas legacy → `recipe`/`recipe_version`/`recipe_components`/`recipe_outputs` (migración **152**, aditiva idempotente; `recetas`+`receta_componentes` y `product_recipes`+`product_recipe_components`; v1 ACTIVE/DRAFT, Decimal). Neutralización de `recipe_engine` → paso 4b | ✅ (backfill) |
| 5 | **Backfill** rendimientos `rendimiento_pollo`+`rendimiento_derivados` → `yield_profiles`/`yield_profile_versions`/`yield_outputs` (migración **153**, aditiva idempotente, Decimal, BY_PRODUCT/MAIN) | ✅ (backfill) |
| 6 | Repuntar compras/producción/BI/fidelidad/forecast a `products.id` | ⏳ |
| 7 | Borrar `modulos/productos.py` + cablear UI enterprise (`ModuloProductosEnterprise`) en `module_loader`/`main_window` | ⏳ |
| 8 | Migrar permisos `PRODUCTOS`→`PRODUCTS_*` y eventos `PRODUCTO_*`→`PRODUCT_*` | ⏳ |
| 9 | Allowlist → vacía; guardrails `test_no_legacy_products_imports` / `test_products_legacy_allowlist_is_empty` | ⏳ |
| 10 | **DROP** destructivo (`PRODUCTS_ALLOW_LEGACY_DROP=1`) de ~20 tablas legacy + trigger | ⏳ |

## 🟢 Bloqueador estructural — RESUELTO (Pricing PRC-0→PRC-9)

El bloqueador #1 (no existía Pricing/Costing canónico) queda **resuelto**: el
bounded context Pricing/Costing está cerrado y verde (PRC-9, 124/124). Precio y
costo tienen destino canónico:
- Precio → `ProductPriceQueryService` / `PricingReadFacade.sale_price`.
- Costo → `ProductCostQueryService` / `PricingReadFacade.unit_cost`.
- Backfill 150 pobló `product_price`/`product_cost` desde el legacy; el costo se
  mantiene fresco por evento (PRC-6).

El bloqueador #2 (existencia acoplada a `productos.existencia`) sigue vigente: los
lectores de POS que no usan `inventory_balances` requieren el mismo repunte que dejó
diferido INV-27.

### ⚠️ Restricción de secuenciación (lección INV-27)

Repuntar **lecturas** de catálogo a `products` mientras las **escrituras** del
maestro siguen en `productos` produce **lecturas obsoletas** (un producto creado en
`productos` no aparecería en `products` hasta el próximo backfill) → regresión. Por
tanto el orden seguro es:

1. **Flip del path de escritura** del maestro a `products` (use case canónico
   create/update + repunte de `modulos/productos.py`), o un sync escritura-dual
   temporal.
2. **Luego** repuntar lecturas de catálogo/búsqueda (paso 3).

Los pasos 4-5 (backfill de recetas y rendimientos legacy → canónico) son
**aditivos** y NO dependen del flip de escritura: pueden ejecutarse antes, con el
mismo método idempotente que 148/150, sin tocar el checkout vivo.

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
