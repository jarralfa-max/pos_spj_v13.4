# PROD-0 — Plan de ejecución del refactor de Productos (Products bounded context)

Plan por fases (PROD-0 → PROD-20) para construir el bounded context canónico de
**Productos / Product Master Data / Material Master / Meat Product Master /
Recipe & BOM Master / Yield & Cutting Master**, siguiendo la REGLA CERO (UUIDv7),
Decimal-only, master-data-driven, unit/weight/lot/variant/recipe-aware,
meat-processing-ready, slaughter-integration-ready, event-driven, security-first y
el Design System JUANIS.

Reemplazo canónico = `backend/domain|application|infrastructure/products` +
`frontend/desktop/modules/products`, mismo patrón que Finance / RRHH / Supplier /
Procurement / Inventory (ya migrados).

**Principio rector:** Productos define *qué es* un artículo. Inventario define
*cuánto y dónde*. Compras *cómo se adquiere*. Producción/Sacrificio *cómo se
transforma*. Calidad *si puede usarse*. Pricing *cuánto se vende*. Ventas/POS
comercializan. Finanzas contabiliza. BI analiza.

**Regla de avance:** no se avanza de fase si los tests de la fase actual no pasan.
**Regla de no-regresión:** cada fase mide node-ids de tests antes/después
(0 nuevas fallas), como en PUR-13/INV-28.

**Fronteras (lo que Productos NO hace):** no almacena existencia, no registra
movimientos, no ejecuta producción/sacrificio, no calcula precio final, no
contabiliza, no calcula rendimiento/costo real de lote. Guardrails lo garantizan.

---

## Estado del árbol (hallazgos PROD-0, ver `products_legacy_inventory.md`)

- **`productos` (tabla m000)** guarda `existencia`/`precio`/`precio_compra`/
  `stock_minimo` en **float**, `categoria`/`unidad` como **texto libre**, y
  `sucursal_id` (**duplicación por sucursal**). `es_compuesto`/`es_subproducto`/
  `es_paquete` como flags en vez de `product_type` canónico.
- **`domain/entities/product.py`** con `id:int` + `precio/existencia: float`
  (viola REGLA CERO + Decimal + "Product no almacena stock").
- **8 tablas de recetas paralelas** (`recetas`, `receta_componentes`,
  `product_recipes`, `product_recipe_components`, `product_recipes_abarrotes`,
  `componentes_producto`, `paquetes_componentes`, `recipe_dependency_graph`) +
  varios motores (`recipe_engine`, `core/services/recipes/*`).
- **Rendimientos solo-pollo / hardcodeados** (`rendimiento_pollo`,
  `rendimiento_derivados`, `meat_production_yields`).
- **Permisos gruesos** (`PRODUCTOS`, `CREAR_PRODUCTO`) y **eventos español ad-hoc**
  (`PRODUCTO_CREADO`, `RECETA_CREADA`).
- Trabajo parcial reutilizable: `backend/application/use_cases/*_product_use_case.py`,
  `product_repository.py`, `product_query_service.py`, `product_type_policy.py`.

---

## Fases

| Fase | Alcance | Entregable | Estado |
| ---- | ------- | ---------- | ------ |
| **PROD-0** | Auditoría: inventario de productos/cárnicos/recetas/rendimientos/cortes/barcodes/unidades/internos; plan | `products_legacy_inventory.md`, `products_refactor_execution_plan.md`, `products_schema_consolidation.md` | ✅ |
| PROD-1 | Seguridad y permisos: permisos granulares `PRODUCTS_*`, alcance por sucursal/tipo, segregación de funciones (crea≠aprueba), autorización en caliente, auditoría | `backend/application/products/authorization/**` + tests | ⏳ |
| PROD-2 | Product Master: entidad `Product` (UUIDv7, tipos/estados/roles), value objects (`product_code`, `product_name`), policies de creación/activación/ciclo de vida | `backend/domain/products/{entities,value_objects,policies,enums,events,exceptions}` + tests | ⏳ |
| PROD-3 | Clasificación cárnica: `Species`, `MeatCategory`, `AnatomicalRegion`, `CutClassification` (jerarquía canal→primario→secundario→porción), multi-especie | `backend/domain/products/entities/*` + policies + tests | ⏳ |
| PROD-4 | Esquema born-clean: `products_schema.py` (UUIDv7, Decimal, constraints, índices, allowlist), migración registrada, bootstrap idempotente | `infrastructure/db/schema/products_schema.py` + migración + tests | ⏳ |
| PROD-5 | Unidades y peso variable: `UnitOfMeasure` (dimensión), `ProductUnitConversion` (Decimal, vigencia, sin ciclos), `CatchWeightConfiguration` (rangos, price_basis, scale barcode) | domain + repos + tests | ⏳ |
| PROD-6 | Productos internos / WIP / semi-terminados: roles (`INTERNAL_ONLY`, `WORK_IN_PROGRESS`…), visibilidad (no POS, sí inventario), policy | domain + tests | ⏳ |
| PROD-7 | Barcodes y etiquetas: `ProductBarcode`/`ProductAlternateCode` (SKU/EAN/UPC/GTIN/PLU/QR/scale/lot/carcass tag), unicidad por policy | domain + repos + tests | ⏳ |
| PROD-8 | Calidad y vida útil: `ProductQualityProfile`, `ProductShelfLifeProfile`, `ProductLogisticsProfile` (cadena de frío, temperatura, caducidad) | domain + repos + tests | ⏳ |
| PROD-9 | Recetas: `Recipe`/`RecipeVersion`/`RecipeComponent`/`RecipeOutput` (venta/producción/procesamiento/despiece/formula), validación de ciclos, versionado | domain + services + repos + tests | ⏳ |
| PROD-10 | Rendimientos: `YieldProfile`/`YieldProfileVersion`/`YieldOutput` (multi-especie, main/co/by-product/waste/loss, tolerancia configurable, sin 100% hardcodeado) | domain + repos + tests | ⏳ |
| PROD-11 | Despiece: `CuttingScheme`/`CuttingSchemeVersion`/`CuttingOutput` (multi-especie, niveles, hueso/sin hueso, peso/pieza) | domain + repos + tests | ⏳ |
| PROD-12 | Preparación para sacrificio: QueryServices de contrato (`AnimalInputConfiguration`, `CarcassProductConfiguration`, `ActiveYieldProfile`, `ActiveCuttingScheme`, `SlaughterOutputDefinition`) sin registrar ejecución real | `application/products/queries/**` + tests | ⏳ |
| PROD-13 | Combos y paquetes: `ProductBundle`/`BundleVersion`/`BundleComponent` (virtual/stocked/meat box/kit), explosión | domain + repos + tests | ⏳ |
| PROD-14 | Sucursales y canales: `BranchProduct`/`Assortment`/`AssortmentProduct` (global/sucursal/POS/e-commerce/WhatsApp/delivery), sin duplicar producto ni precio operativo | domain + repos + tests | ⏳ |
| PROD-15 | Catálogos externos: `ExternalCatalogSource`/`ExternalProductRecord`/`ProductImportBatch`, gateway + registry + adapters (Open Food Facts / supplier / CSV), matching + provenance | `infrastructure/product_catalogs/**` + tests | ⏳ |
| PROD-16 | Notificaciones y WhatsApp: policies + `ProductNotificationGateway` (in-app + WhatsApp), alertas (producto incompleto, barcode duplicado, receta circular, rendimiento fuera de tolerancia, cárnico sin especie/calidad, versión por vencer) | `application/products/notification_handlers/**` + gateway + tests | ⏳ |
| PROD-17 | Integraciones: Inventario, Compras, POS/Ventas, Pricing, Producción, Calidad, BI (todas por `product_id` + QueryServices; Productos no lee balances ni fija precio) | event_handlers + queries + tests | ⏳ |
| PROD-18 | UI/UX enterprise: `frontend/desktop/modules/products/**` (view/presenter/routes/view_models, páginas §42, tema JUANIS, componentes DS, sin SQL/estilos locales, 1366×768, claro/oscuro) | frontend + guardrails | ⏳ |
| PROD-19 | Eliminación de legacy: descomponer y borrar `modulos/productos.py`, recetas/rendimientos legacy, tablas duplicadas, imports, permisos/eventos legacy; allowlist → vacía; reporte | `products_legacy_removal_report.md` + allowlist | ⏳ |
| PROD-20 | Validación final: suites dominio/aplicación/integración/UI/seguridad/arquitectura + bootstrap limpio + auditorías (UUIDv7, Decimal, sin SQL en UI, sin stock/precio en Product, recetas/rendimientos/especies/permisos/legacy) | reporte de validación + `module_relocation_map.md` → MIGRATED | ⏳ |

---

## Guardrails de arquitectura (a crear conforme avanza)

```
tests/architecture/test_products_ui_uses_query_services.py
tests/architecture/test_products_ui_uses_use_cases.py
tests/architecture/test_products_ui_has_no_database_access.py
tests/architecture/test_products_ui_has_no_inline_styles.py
tests/architecture/test_products_have_no_hardcoded_colors.py
tests/architecture/test_products_use_standard_components.py
tests/architecture/test_products_use_decimal.py
tests/architecture/test_products_use_uuidv7.py
tests/architecture/test_product_master_does_not_store_stock.py
tests/architecture/test_product_master_does_not_own_pricing.py
tests/architecture/test_products_do_not_execute_inventory.py
tests/architecture/test_products_do_not_execute_production.py
tests/architecture/test_meat_products_are_not_chicken_only.py
tests/architecture/test_product_permissions_are_granular.py
tests/architecture/test_product_notifications_use_gateway.py
tests/architecture/test_no_legacy_products_imports.py
tests/architecture/test_products_legacy_allowlist_is_empty.py
```

## Definición de terminado (resumen §52)

Un solo Product Master (UUIDv7, Decimal, sin stock, sin precio final), multi-especie
con clasificación cárnica y cortes jerárquicos, peso variable, productos
internos/WIP/no-vendibles, coproductos/subproductos/residuos, recetas y rendimientos
y despiece versionados, preparado para sacrificio (sin ejecutarlo), lotes/caducidad/
cadena de frío/calidad configurables, unidades/conversiones/barcodes de báscula,
sucursales/surtidos, combos, notificaciones + WhatsApp, permisos granulares +
segregación + auditoría, Design System JUANIS (claro/oscuro, 1366×768), sin SQL en
UI, sin floats, sin `modulos/productos.py` funcional, sin services/repos/tablas/
imports legacy, allowlist vacía, bootstrap limpio, suite verde.
