# PROD-0/PROD-4 — Consolidación de esquema de Productos

Mapa de tablas legacy → esquema canónico born-clean (`products_schema.py`, UUIDv7
`TEXT PRIMARY KEY` en SQLite / `UUID` en PostgreSQL, cantidades/pesos/rendimientos en
Decimal, catálogos como FK y no texto libre). Acciones: `REUSE | ALTER | MERGE |
REPLACE | DROP`. Se materializa en PROD-4; aquí se fija el destino.

## 1. Maestro de producto

| Legacy | Canónico | Acción |
| ------ | -------- | ------ |
| `productos` (float precio/existencia, categoria/unidad texto, sucursal_id, flags es_*) | `products` (product_type enum, lifecycle_status, category_id/brand_id/base_unit_id FK, flags booleanos de control: sellable/purchasable/inventory_managed/producible/internal_only/lot_controlled/expiration_controlled/catch_weight_enabled/quality_controlled/traceability_required; **sin existencia, sin precio final**) | REPLACE |
| `productos.existencia`, `stock_minimo` | Inventory bounded context (`inventory_balances`) | DROP (migrado) |
| `productos.precio`, `precio_compra`, `precio_minimo_venta` | Pricing bounded context | DROP (migrado) |
| `branch_products` (precio_local/stock_min_local REAL) | `branch_product` + `assortment` / `assortment_product` (habilitación por sucursal/canal; sin precio operativo) | REPLACE |

## 2. Clasificación cárnica (nuevo)

| Canónico | Notas |
| -------- | ----- |
| `species` | POULTRY/BOVINE/PORCINE/OVINE/CAPRINE/RABBIT/FISH/SEAFOOD/OTHER |
| `meat_category` | LIVE/CARCASS/…/BY_PRODUCT/WASTE |
| `anatomical_region` | configurable por especie |
| `cut_classification` | jerárquico (`parent_cut_id`), bone/fat/grade |

Reemplaza `cortes_caja_erp`, `inventario_subproductos` (REPLACE) y el hardcode de
solo-pollo.

## 3. Unidades y conversiones

| Legacy | Canónico | Acción |
| ------ | -------- | ------ |
| `unidades_medida` | `unit_of_measure` (dimensión WEIGHT/COUNT/VOLUME/…) | ALTER/REPLACE (UUIDv7) |
| `unidades_conversion` | `product_unit_conversion` (Decimal, vigencia, redondeo, sin ciclos) | ALTER/REPLACE |
| — | `catch_weight_configuration` (rangos, price_basis, scale barcode) | nuevo |

## 4. Códigos / barcodes

| Legacy | Canónico | Acción |
| ------ | -------- | ------ |
| `productos.codigo`, `codigo_barras` | `product_barcode` (SKU/EAN/UPC/GTIN/PLU/QR/SCALE_BARCODE/LOT_LABEL/CARCASS_TAG) + `product_alternate_code` (supplier code) | REPLACE |

## 5. Recetas / BOM (colapsar 8 → 4)

| Legacy | Canónico | Acción |
| ------ | -------- | ------ |
| `recetas`, `receta_componentes`, `product_recipes`, `product_recipe_components`, `product_recipes_abarrotes`, `componentes_producto`, `paquetes_componentes`, `recipe_dependency_graph` | `recipe`, `recipe_version`, `recipe_component`, `recipe_output` (tipos SALES_EXPLOSION/PRODUCTION_BOM/PROCESSING/DISASSEMBLY/CUTTING_YIELD/FORMULA/…; versionado; validación de ciclos) | MERGE → REPLACE |

## 6. Rendimientos

| Legacy | Canónico | Acción |
| ------ | -------- | ------ |
| `rendimiento_pollo`, `rendimiento_derivados`, `meat_production_yields`, `production_yield_analysis` | `yield_profile`, `yield_profile_version`, `yield_output` (multi-especie; output_type MAIN/CO/BY_PRODUCT/WASTE/LOSS; tolerancia configurable) | REPLACE |

## 7. Despiece

| Canónico | Notas |
| -------- | ----- |
| `cutting_scheme`, `cutting_scheme_version`, `cutting_output` | multi-especie, niveles, hueso/sin hueso, peso/pieza |

## 8. Combos / paquetes

| Legacy | Canónico | Acción |
| ------ | -------- | ------ |
| `paquetes_componentes`, `contenedor_productos` | `product_bundle`, `bundle_version`, `bundle_component` (virtual/stocked/meat box/kit) | MERGE → REPLACE |

## 9. Calidad / logística / vida útil (nuevo)

`product_quality_profile`, `product_shelf_life_profile`, `product_logistics_profile`,
`product_tax_profile`, `product_sales_profile`, `product_purchase_profile`,
`product_image`, `product_attribute_definition`, `product_attribute_value`.

## 10. Catálogos externos (nuevo)

`external_catalog_source`, `external_product_record`, `product_import_batch`.

## 11. Fuera de Productos (MOVE, no en este esquema)

`meat_production_runs`, `production_batches`, `production_outputs`,
`production_cost_ledger`, `production_alerts` → Production bounded context.

## 12. Consumidores externos (REUSE, repuntar FK a `products.id`)

`bi_product_profit`, `product_forecast_config`, `raffle_eligible_products`,
`contenedor_productos` (QR compras). Se validan en PROD-19.

## 13. DROP final (PROD-19, tras cero consumidores)

`productos`, `branch_products` (legacy), las 8 tablas de recetas, rendimientos
solo-pollo, `cortes_caja_erp`, `inventario_subproductos`, `productos_deletion_guard`
y triggers asociados. Migración diferida `migrations/deferred/legacy_products_drop.py`
(no registrada, env-guard), como en Inventory.
