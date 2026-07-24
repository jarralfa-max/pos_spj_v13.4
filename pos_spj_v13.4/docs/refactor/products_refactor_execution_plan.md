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
| **PROD-1** | Seguridad y permisos: 60 permisos granulares `PRODUCTS_*` (`ProductPermissions`, sin permiso grueso `PRODUCTOS`), `ProductsAuthorizationPolicy` (require/has, segregación crea≠aprueba/activa vía `SEGREGATED_APPROVALS`, alcance por sucursal + visibilidad internos/cárnicos, autorización en caliente → `ProductAuthorizationGrant`), auditoría `ProductAuditEntry` (§40, UUIDv7) | `backend/application/products/{permissions,authorization/**}` + `backend/domain/products/{exceptions,value_objects}` + tests (25) | ✅ |
| **PROD-2** | Product Master: entidad `Product` (UUIDv7, **sin existencia/precio**, 25 `ProductType`, 7 `LifecycleStatus`, 9 `ProductRole` derivados de banderas, `is_meat`/`is_sellable_now`, transiciones válidas), VOs `ProductCode`/`ProductName` (normalizados), policies de creación/activación/ciclo de vida (tabla única de transiciones), eventos canónicos `PRODUCT_*` (sin `PRODUCTO_CREADO` legacy) | `backend/domain/products/{entities,value_objects,policies,enums,events,exceptions}` + tests (27) | ✅ |
| **PROD-3** | Clasificación cárnica **multi-especie** (nunca solo pollo): enums `MeatSpeciesCode` (9)/`MeatCategory` (16)/`BoneStatus`/`FatClass`/`CutLevel`; entidades catálogo `Species`, `AnatomicalRegion` (scoped por especie), `CutClassification` (jerarquía canal→primario→secundario→porción con `validate_under_parent`: misma especie + nivel estrictamente inferior, sin auto-padre); `meat_product_classification_policy` (cárnico exige especie, corte coherente con especie/región) | `backend/domain/products/{meat_enums,entities,policies}` + tests (17) | ✅ |
| **PROD-4** | Esquema born-clean `products_schema.py` (8 tablas canónicas: `products` **sin existencia/precio**, `species`/`anatomical_regions`/`cut_classifications`, `product_authorization_log`/`product_audit_log`, `product_outbox`/`product_processed_events`; TEXT PK UUIDv7, sin REAL, flags INTEGER CHECK, catálogos por FK, UNIQUE code/species+code, índices), migración **136** registrada en engine, bootstrap limpio idempotente (121 migraciones OK) | `infrastructure/db/schema/products_schema.py` + `migrations/standalone/136_*` + tests (10) | ✅ |
| **PROD-5** | Unidades y peso variable: enums `UnitDimension`/`PriceBasis`; `UnitOfMeasure` (dimensión), `ProductUnitConversion` (factor **Decimal** >0, vigencia, redondeo, global o por producto), `unit_conversion_policy` (detección de ciclos DFS + conversión por camino BFS con factor inverso, sin float), `CatchWeightConfiguration` (rango min/avg/max, tolerancia 0-100 %, `price_basis`, scale barcode, `is_weight_in_range`); `UnitRepository` (round-trip Decimal↔str) + esquema (units/conversions/catch-weight) + migración **137** | `backend/domain/products/{unit_enums,entities,value_objects,policies}` + `infrastructure/db/repositories/products/unit_repository.py` + migración 137 + tests (39) | ✅ |
| **PROD-6** | Productos internos / WIP / semi-terminados: enum `InternalStage` (NONE/INTERNAL_ONLY/WORK_IN_PROGRESS/SEMI_FINISHED/PROCESS_INTERMEDIATE); `Product.internal_stage` (fuerza `internal_only`, choca con `sellable`), helpers `is_internal`/`is_work_in_progress`/`is_visible_in_pos`/`can_be_recipe_component`; `internal_product_policy` (interno no vendible/no-POS, `is_transformation` = producto distinto no identidad mutada); columna `internal_stage` + migración **138** | `backend/domain/products/{internal_enums,entities/product,policies}` + migración 138 + tests (16) | ✅ |
| **PROD-7** | Barcodes y etiquetas: enum `BarcodeType` (11: SKU/EAN/UPC/GTIN/PLU/QR/supplier/scale/lot/carcass/custom); VO `Barcode` (checksum GS1 EAN-13/UPC-A/GTIN, numérico), `ScaleBarcodeFormat`/`parse_scale_barcode` (peso/precio embebido Decimal, formato configurable §12); entidades `ProductBarcode`/`ProductAlternateCode`; `barcode_uniqueness_policy` (activo = un producto); `BarcodeRepository` + esquema (índice parcial UNIQUE en activos) + migración **139** | `backend/domain/products/{barcode_enums,value_objects,entities,policies}` + `repositories/products/barcode_repository.py` + migración 139 + tests (24) | ✅ |
| **PROD-8** | Calidad y vida útil: VO `TemperatureRange` (Decimal, min≤max, `contains`); `ProductShelfLifeProfile` (días enteros, gates recepción/venta, ventana); `ProductQualityProfile` (inspección/temp/peso/organoléptico/microbio, bandas grasa/humedad Decimal 0-100, `fat_in_range`); `ProductLogisticsProfile` (pesos Decimal, temperaturas de almacén/transporte, frozen/chilled→cadena de frío); `shelf_life_policy` (perecedero exige perfil §35); `ProfileRepository` + esquema (3 tablas) + migración **140** | `backend/domain/products/{value_objects,entities,policies}` + `repositories/products/profile_repository.py` + migración 140 + tests (23) | ✅ |
| **PROD-9** | Recetas versionadas: enums `RecipeType` (10)/`RecipeVersionStatus` (6)/`OutputType` (5); entidades `Recipe`/`RecipeVersion` (transiciones DRAFT→…→ACTIVE, inmutable en APPROVED/ACTIVE §22)/`RecipeComponent` (Decimal, scrap, `gross_quantity`)/`RecipeOutput` (yield 0-100); servicios `recipe_cycle_policy` (ciclo directo+transitivo con resolver), `RecipeValidationService` (componentes distintos, auto-consumo, multi-output exige outputs), `RecipeExplosionService` (explosión Decimal con/sin scrap); `RecipeRepository` (+ resolver sobre versión ACTIVA) + esquema (4 tablas) + migración **141** | `backend/domain/products/{recipe_enums,entities,services}` + `repositories/products/recipe_repository.py` + migración 141 + tests (25) | ✅ |
| **PROD-10** | Rendimientos **multi-especie**: `YieldProfile` (input+especie), `YieldProfileVersion` (versionado §22 + `tolerance_pct` configurable), `YieldOutput` (MAIN/CO/BY_PRODUCT/WASTE/LOSS, `expected_yield_pct` + banda min/max, `cost_allocation_weight`, Decimal); `YieldValidationService` (suma ≈100 % dentro de **tolerancia configurable — sin 100 % hardcodeado**, outputs distintos); `YieldRepository` (+ versión ACTIVA por input) + esquema (3 tablas) + migración **142** | `backend/domain/products/{entities,services}` + `repositories/products/yield_repository.py` + migración 142 + tests (18) | ✅ |
| **PROD-11** | Despiece **multi-especie**: `CuttingScheme` (input+especie+`cut_level`, exige especie §24), `CuttingSchemeVersion` (versionado §22), `CuttingOutput` (`MeasureKind` BY_PIECE/BY_WEIGHT, `bone_status`, `cut_level`, `cut_classification_id`, OutputType, Decimal); `CuttingSchemeService` (outputs distintos, sin auto-contención §24); `CuttingSchemeRepository` (+ versión ACTIVA por input, para faena §25) + esquema (3 tablas) + migración **143** | `backend/domain/products/{entities,services}` + `repositories/products/cutting_scheme_repository.py` + migración 143 + tests (15) | ✅ |
| **PROD-12** | Preparación para sacrificio: 5 QueryServices de contrato **solo lectura** (`AnimalInputConfiguration`, `CarcassProductConfiguration` [+ shelf-life/logística/calidad], `ActiveYieldProfile`, `ActiveCuttingScheme`, `SlaughterOutputDefinition` = unión de outputs) sobre las tablas canónicas PROD-10/11 + DTOs Decimal-safe; Productos **no registra ejecución real** (guardrail: sin métodos record/save/execute/slaughter) | `backend/application/products/queries/{slaughter_config_dtos,slaughter_config_query_service}.py` + tests (9) | ✅ |
| **PROD-13** | Combos y paquetes: enum `BundleType` (8: virtual/stocked/meat box/kit/gift set/mix-and-match…); `ProductBundle` (`is_virtual`/`is_stocked`), `BundleVersion` (versionado §22), `BundleComponent` (Decimal, optional/substitutable); `BundleExplosionService` (validación auto-contención directa+transitiva, explosión Decimal excluyendo opcionales); `BundleRepository` (+ versión ACTIVA + resolver ciclos) + esquema (3 tablas) + migración **144** | `backend/domain/products/{bundle_enums,entities,services}` + `repositories/products/bundle_repository.py` + migración 144 + tests (16) | ✅ |
| **PROD-14** | Sucursales y canales: enum `SalesChannel` (8: GLOBAL/POS/ECOMMERCE/WHATSAPP/DELIVERY/WHOLESALE/PLANT/CENTRAL_WAREHOUSE) + `CONSUMER_CHANNELS`; `BranchProduct` (habilitación por sucursal, **sin precio ni stock** — un producto, muchas sucursales), `Assortment`/`AssortmentProduct` (surtido curado por canal); `branch_assortment_policy` (canales de consumo no exponen internos/no-vendibles §13/§33); `BranchAssortmentRepository` (UNIQUE product+branch) + esquema canónico singular `branch_product` (no colisiona con legacy `branch_products`) + migración **145** | `backend/domain/products/{channel_enums,entities,policies}` + `repositories/products/branch_assortment_repository.py` + migración 145 + tests (15) | ✅ |
| **PROD-15** | Catálogos externos: enums `ExternalProviderType`/`ExternalRecordStatus`/`ImportBatchStatus`; VO `DataQualityScore` (0-100 por completitud); entidades `ExternalCatalogSource`/`ExternalProductRecord` (provenance + review→import)/`ProductImportBatch`; `ProductMatchingService` (barcode→nombre normalizado), `external_data_acceptance_policy` (requiere revisión + calidad mín); infra `ExternalProductCatalogGateway` (Protocol adapter) + `ProviderRegistry` + `external_record_normalizer` + adapters `CsvCatalogAdapter`/`OpenFoodFactsAdapter`/`SupplierCatalogAdapter` (fetch inyectado, sin red); `ExternalCatalogRepository` + esquema (3 tablas) + migración **146** | `backend/domain/products/**` + `backend/infrastructure/product_catalogs/**` + `repositories/products/external_catalog_repository.py` + migración 146 + tests (23) | ✅ |
| **PROD-16** | Notificaciones y WhatsApp: enums `NotificationSeverity`/`NotificationChannel`/`ProductAlertType` (17 alertas §35); `ProductNotificationGateway` (Protocol + `InMemoryProductNotifier`); `notification_policy` (severidad + canales, **WhatsApp solo alto impacto §36**); `ProductNotificationService` (entrega, **throttle** por alerta/entidad/canal/destinatario, audit SENT/FAILED/THROTTLED, eventos PRODUCT_NOTIFICATION_CREATED/WHATSAPP_ALERT_SENT); detectores `product_alert_detectors` (incompleto/cárnico sin especie/perecedero sin vida útil/peso sin rango/sin calidad/pendiente/discontinuado activo) + esquema `product_notification_log` + migración **147** | `backend/domain/products/notification_enums.py` + `backend/application/products/{notifications,notification_handlers}/**` + migración 147 + tests (14) | ✅ |
| **PROD-17** | Integraciones por `product_id`: DTOs + 4 QueryServices de lectura (`InventoryProductConfig` §30, `PurchaseProductConfig` §31 con supplier codes/cadena de frío, `PosCatalog` §33 `sellable_now`/`is_offered_at_branch`/barcode/bundle/receta **sin precio**, `QualityProductConfig` §34); handler `QualityStatusHandler` (PRODUCT_QUALITY_BLOCKED/RELEASED → bloquea/libera estado comercial vía caso autorizado, idempotente por event_id, audit, **sin tocar stock**); guardrail AST `test_products_integration_boundaries` (Productos no lee balances ni devuelve precio) | `backend/application/products/{queries,event_handlers}/**` + tests (17) | ✅ |
| **PROD-18** | UI/UX enterprise `frontend/desktop/modules/products/**`: `view_models` (mappers es-MX tipo/estado/severidad + `TableViewModel`/`KpiViewModel`), `navigation` (21 páginas declarativas §42 con permiso granular `PRODUCTS_*` + `visible_entries`), `ProductsPresenter` (KPIs/catálogo/alertas → view-models, sin SQL), `routes` (page_id→página lazy), páginas presentation-only `ProductsOverviewPage`/`ProductCatalogPage` (componentes JUANIS, sin SQL/estilos locales); `ProductCatalogReadService` (SQL en application) + guardrail UI-sin-SQL | `frontend/desktop/modules/products/**` + `backend/application/products/queries/catalog_read_service.py` + tests (10) | ✅ |
| PROD-19 | **Corte atómico** (aprobado; incremental, cero regresiones). Paso 1 ✅ backfill `productos`→`products` (migración 148, sin precio/existencia). Paso 2 ✅ DROP diferido `legacy_products_drop.py` (env-guard, no registrado) + `products_legacy_removal_report.md` (10 pasos). Pasos 3-10 ⏳: repuntar POS/Ventas/Compras/Producción/BI a `products.id`, migrar recetas/rendimientos legacy, borrar `modulos/productos.py` + UI enterprise, migrar permisos/eventos legacy, allowlist→vacía, DROP | `migrations/{standalone/148,deferred/legacy_products_drop}` + `products_legacy_removal_report.md` + tests (10) | 🔄 (2/10) |
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
