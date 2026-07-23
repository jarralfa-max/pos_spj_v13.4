# PROD-0 — Inventario de legacy del bounded context de Productos

Auditoría previa a la construcción del **Product Master canónico** (Productos /
Product Master Data / Material Master / Meat Product Master / Recipe & BOM Master).
Sigue `SPJ_REFACTOR_SKILL.md` (REGLA CERO UUIDv7, Decimal-only, backend inglés / UI
español, sin SQL en UI, sin rutas paralelas) y el patrón de los contextos ya
migrados (Finance / RRHH / Supplier / Procurement / Inventory).

Estados de clasificación: `REUSE | MOVE | WRAP_TEMPORARILY | REWRITE | DELETE | BLOCKED`.
Todo `BLOCKED` incluye su condición de desbloqueo.

---

## 1. Superficie legacy encontrada

### 1.1 UI (PyQt5)

| Archivo | Líneas | Rol | Clasificación |
| ------- | ------ | --- | ------------- |
| `modulos/productos.py` | 1534 | Ventana de catálogo + diálogo de alta/edición con tabs (Precios/Costos, stock, subproductos, paquetes). Usa `QDoubleSpinBox` (float) para precio/costo/stock_minimo/precio_minimo; SQL embebido (5 sitios). | **REWRITE** → `frontend/desktop/modules/products/` |
| `modulos/dialogs/receta_dialog.py` | — | Diálogo legacy de recetas. | **REWRITE** → `dialogs/recipe_dialog.py` + `recipe_version_dialog.py` |
| `modulos/spj_product_search.py` | — | Buscador de productos legacy. | **REWRITE** → `EntitySearchInput` del Design System |
| `frontend/desktop/components/product_search_box.py` | — | Componente de búsqueda. | **REUSE/REVIEW** (si ya es Design System) |

### 1.2 Dominio / entidades

| Archivo | Problema | Clasificación |
| ------- | -------- | ------------- |
| `domain/entities/product.py` | `id: int`, `precio: float`, `existencia: float`, `categoria: str`. Viola REGLA CERO (int id), Decimal-only y "Product no almacena stock". | **REWRITE** → `backend/domain/products/entities/product.py` (UUIDv7, sin stock, sin precio final) |
| `backend/domain/services/product_type_policy.py` | Policy de tipo de producto (parcial). | **REUSE/MOVE** → `domain/products/policies/` |

### 1.3 Aplicación (casos de uso / queries / commands)

| Archivo | Clasificación |
| ------- | ------------- |
| `backend/application/use_cases/create_product_use_case.py` | **MOVE/REWRITE** → `application/products/use_cases/` |
| `backend/application/use_cases/update_product_use_case.py` | **MOVE/REWRITE** |
| `backend/application/use_cases/deactivate_product_use_case.py` | **MOVE/REWRITE** |
| `backend/application/use_cases/restore_product_use_case.py` | **MOVE/REWRITE** |
| `backend/application/use_cases/execute_meat_production_use_case.py` | **MOVE** → Production bounded context (no es Productos; ejecuta transformación) |
| `backend/application/commands/product_commands.py` | **MOVE/REWRITE** |
| `backend/application/queries/product_query_service.py` | **MOVE/REWRITE** → `application/products/queries/` |
| `backend/application/services/product_catalog_service.py` | **REWRITE** |
| `backend/application/services/product_image_service.py` | **MOVE** → `infrastructure/media/` gateway |
| `core/services/product_catalog_query_service.py` / `core/services/sales/product_catalog_query_service.py` | **DELETE** (duplicados; consolidar en un solo QueryService de Productos) |

### 1.4 Repositorios

| Archivo | Clasificación |
| ------- | ------------- |
| `backend/infrastructure/db/repositories/product_repository.py` | **REWRITE** → `infrastructure/db/repositories/products/product_repository.py` (Decimal, sin existencia/precio) |
| `backend/infrastructure/db/repositories/branch_product_repository.py` | **MOVE/REWRITE** → `products/branch_product_repository.py` |
| `repositories/productos.py` | **DELETE** (repo legacy) |
| `repositories/recetas.py` | **DELETE** (repo legacy de recetas) |

### 1.5 Motores de recetas (SPRAWL — múltiples implementaciones paralelas)

| Archivo | Clasificación |
| ------- | ------------- |
| `core/services/recipes/recipe_service.py` | **REWRITE** → `domain/products/services/recipe_*` + `application/products/use_cases/` |
| `core/services/recipes/recipe_validation_service.py` | **REWRITE** → `domain/products/services/recipe_validation_service.py` |
| `core/services/recipes/recipe_resolver.py` | **REWRITE** → `domain/products/services/recipe_explosion_service.py` |
| `core/services/recipe_engine.py` | **DELETE/REWRITE** (motor legacy monolítico) |
| `core/production/yield_calculator.py`, `core/production/cost_allocator.py`, `core/production/production_engine.py` | **MOVE** → Production bounded context (Productos sólo define YieldProfile/CuttingScheme, no calcula rendimiento real) |

### 1.6 Tablas (esquema)

Fuente de verdad legacy = tabla `productos` (m000). Anti-patrones detectados:

| Tabla | Problema | Acción |
| ----- | -------- | ------ |
| `productos` | `precio REAL`, `precio_compra REAL`, `precio_minimo_venta REAL`, `existencia REAL`, `stock_minimo REAL` (stock+precio dentro del producto, float), `categoria TEXT`, `unidad TEXT` (catálogos como texto libre), `sucursal_id TEXT` (duplicación por sucursal), `es_compuesto/es_subproducto/es_paquete` (flags en vez de tipo canónico) | **REPLACE** → `products` (UUIDv7, sin stock, sin precio final, `category_id`/`base_unit_id` FK, `product_type` enum) |
| `branch_products` | `precio_local REAL`, `stock_min_local REAL` + vista de compat que lee `productos.sucursal_id` | **REPLACE** → `branch_product` / `assortment` (habilitación por sucursal/canal, sin precio operativo) |
| `recetas`, `receta_componentes`, `product_recipes`, `product_recipe_components`, `product_recipes_abarrotes`, `componentes_producto`, `paquetes_componentes`, `recipe_dependency_graph` | **8 sistemas de recetas paralelos** | **MERGE → REPLACE** por `recipe` / `recipe_version` / `recipe_component` / `recipe_output` |
| `rendimiento_pollo`, `rendimiento_derivados`, `meat_production_yields`, `production_yield_analysis` | Rendimientos hardcodeados / solo pollo | **REPLACE** → `yield_profile` / `yield_profile_version` / `yield_output` (multi-especie, versionado, tolerancia) |
| `cortes_caja_erp`, `inventario_subproductos` | Cortes/subproductos legacy | **REPLACE** → `species` / `meat_category` / `anatomical_region` / `cut_classification` + `cutting_scheme*` |
| `unidades_medida`, `unidades_conversion` | Unidades base | **REUSE/ALTER** → `unit_of_measure` / `product_unit_conversion` (UUIDv7, Decimal, dimensión) |
| `contenedor_productos`, `raffle_eligible_products`, `bi_product_profit`, `product_forecast_config` | Consumidores externos (Compras QR, Fidelidad, BI, Forecast) | **REUSE** (repuntar FK a `products.id`) |
| `meat_production_runs`, `production_batches`, `production_outputs`, `production_cost_ledger`, `production_alerts` | Ejecución de producción | **MOVE** → Production bounded context (fuera de Productos) |
| `productos_deletion_guard` | Trigger legacy de borrado | **DROP** al final |

Consolidación detallada en `products_schema_consolidation.md` (PROD-4).

### 1.7 Permisos legacy (por nombre / gruesos)

`PRODUCTOS`, `PRODUCTO`, `CREAR_PRODUCTO`, `ACTUALIZAR_PRODUCTO`, `SUBPRODUCTO`,
`ADMIN_PRODUCTOS` → **REPLACE** por permisos granulares `PRODUCTS_*` (§38 del prompt).

### 1.8 Eventos legacy (español / ad-hoc)

`PRODUCTO_CREADO`, `PRODUCTO_ACTUALIZADO`, `PRODUCTO_ELIMINADO`, `nuevo_producto`,
`RECETA_CREADA`, `RECETA_ACTUALIZADA`, `RECETA_CICLICA`, `RECETA_NO_ENCONTRADA`,
`RECETA_SIN_COMPONENTES`, … → **MAP** a eventos canónicos `PRODUCT_*` /
`PRODUCT_RECIPE_*` / `MEAT_PRODUCT_*` post-commit (§46).

---

## 2. Reglas de negocio a preservar (no perder)

- Alta/edición de producto con código, nombre, categoría, unidad, imagen.
- Productos compuestos / paquetes / subproductos (→ `product_type` + `product_bundle`).
- Precio mínimo de venta como protección financiera (→ Pricing bounded context, no Product).
- Recetas de venta (descomposición al vender) y de producción/compra (explosión).
- Rendimientos cárnicos (hoy `rendimiento_pollo`) → generalizar multi-especie.
- Cortes / subproductos / coproductos / merma teórica.
- Búsqueda de producto por código/barcode/nombre normalizado.
- Guard de borrado (no eliminar producto con historial).

---

## 3. Consumidores a repuntar antes de eliminar `productos`

POS/Ventas, Inventario (ya canónico, lee `product_id`), Compras (QR/recepción),
Producción, Fidelidad (`raffle_eligible_products`), BI (`bi_product_profit`),
Forecast (`product_forecast_config`), Delivery, WhatsApp. Se enumeran y verifican
"cero consumidores" en PROD-19 antes del DROP (allowlist vacía = terminado).

---

## 4. Riesgo principal

`modulos/productos.py` + tabla `productos` están **profundamente acoplados** a POS,
Inventario, Compras y Producción por `product_id` y por columnas `existencia`/`precio`.
La estrategia (como Inventario) es: construir el Product Master canónico born-clean,
migrar consumidores por eventos/QueryServices, y sólo entonces hacer el corte +
DROP. `existencia` y `precio` salen de Product hacia Inventory y Pricing
respectivamente (guardrails `test_product_master_does_not_store_stock` /
`test_product_master_does_not_own_pricing`).
