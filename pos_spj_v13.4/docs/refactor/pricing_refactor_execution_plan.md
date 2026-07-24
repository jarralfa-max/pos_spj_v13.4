# PRC-0 — Plan de ejecución del refactor de Pricing / Costing (Pricing bounded context)

Plan por fases (PRC-0 → PRC-9) para construir el contexto canónico de **Precios y
Costos**, born-clean (UUIDv7), Decimal/Money-only, event-driven, security-first,
Design System JUANIS. Su meta operativa: **desbloquear el DROP de `productos`**
(PROD-19) dando a POS/BI/Compras un destino canónico para leer precio y costo.

Reemplazo canónico = `backend/domain|application|infrastructure/pricing` +
`frontend/desktop/modules/pricing`, mismo patrón que Finance / Inventory / Products.

**Principio rector:** Pricing fija cuánto se vende; Costing calcula cuánto cuesta.
Productos define *qué es* el artículo (no su precio). Compras/Producción alimentan
el costo. Ventas/POS leen el precio. Finanzas contabiliza márgenes.

**Regla de avance:** no se avanza si los tests de la fase no pasan.
**Regla de no-regresión:** node-ids antes/después (0 fallas nuevas) + bootstrap
limpio, como en INV/PROD.

---

## Hallazgos (PRC-0, ver `pricing_legacy_inventory.md`)

- Precio/costo viven en columnas `productos.precio/precio_compra/costo/costo_
  promedio/precio_minimo` + `branch_products.precio_local` + tablas `listas_precio`/
  `precios_lista`/`precios_volumen`/`clientes_lista_precio` + `historial_precios`.
- `core/services/pricing_service.py` (158) usa `producto_id:int` (viola REGLA CERO)
  y precios float. Prioridad de resolución: volumen > lista cliente > lista > base.
- **44** consumidores leen precio/costo desde `productos`/`precios_lista`.

---

## Fases

| Fase | Alcance | Entregable | Estado |
| ---- | ------- | ---------- | ------ |
| **PRC-0** | Auditoría + plan | `pricing_legacy_inventory.md`, `pricing_refactor_execution_plan.md` | ✅ |
| **PRC-1** | Seguridad: 22 permisos granulares `PRICING_*` (`PricingPermissions`, incl. `VIEW_COST`/`PRICE_MIN_OVERRIDE`/`LIST_APPROVE`/`COST_MANAGE`); `PricingAuthorizationPolicy` (require/has, segregación crea≠aprueba lista vía `SEGREGATED_APPROVALS`, alcance por sucursal, hot-auth → `PricingAuthorizationGrant` para venta bajo precio mínimo); excepciones base | `backend/application/pricing/{permissions,authorization/**}` + `backend/domain/pricing/{exceptions,value_objects}` + tests (18) | ✅ |
| **PRC-2** | Dominio: VO `Money` (Decimal + moneda ISO, aritmética con guard de moneda, sin float), `MarginPolicy` (precio mínimo + margen objetivo → `target_price_from_cost`); enums (`PriceListStatus`/`PriceListKind`/`CostMethod`/`PriceSource`); entidades `PriceList` (ciclo DRAFT→…→ACTIVE, inmutable APPROVED/ACTIVE, sin auto-herencia, descuento 0-100), `ProductPrice`/`VolumePrice` (Money, tiers por cantidad), `ProductCost` (avg/last/standard, `effective_cost`); eventos `PricingEvents` (sin `PRECIO_ACTUALIZADO` legacy) | `backend/domain/pricing/{value_objects,entities,enums,events,exceptions}` + tests (24) | ✅ |
| **PRC-3** | Esquema born-clean `pricing_schema.py` (8 tablas: `price_list`, `product_price`, `volume_price`, `customer_price_list`, `product_cost`, `price_change_log`, `pricing_authorization_log`, `pricing_outbox`; TEXT PK UUIDv7, Money = TEXT Decimal + `*_currency`, **sin REAL**, UNIQUE code/dimensión, índices), migración **149** registrada, bootstrap limpio | `infrastructure/db/schema/pricing_schema.py` + `migrations/standalone/149_*` + tests (9) | ✅ |
| **PRC-4** | Resolución + query services: `PricingResolutionService` (prioridad **volumen > lista cliente > lista > base**, descuento a lista/base no a volumen, flag `below_minimum` respetando precio mínimo → `PriceResolution`); `ProductPriceQueryService.get_sale_price(product, branch, customer, channel, quantity)` + `ProductCostQueryService.get_average_cost/get_effective_cost`; `PricingRepository` (Money↔TEXT, branch '' = todas, tiers/costo/lista de cliente) | `backend/domain/pricing/services/**` + `application/pricing/queries/**` + `repositories/pricing/pricing_repository.py` + tests (15) | ✅ |
| **PRC-5** | Backfill **150** (idempotente, Decimal-only, aditivo): `productos.precio`/`precio_minimo*` → `product_price` (lista **BASE**); `productos.costo_promedio\|costo`/`precio_compra` → `product_cost`; `listas_precio` → `price_list` (kind CUSTOMER, descuento %); `precios_lista` → `product_price` (por lista); `precios_volumen` → `volume_price` (tiers); `clientes_lista_precio` → `customer_price_list`; `branch_products.precio_local` → `product_price` (override sucursal). Detección defensiva de columnas, omite valores ≤0, sin REAL | `migrations/standalone/150_*` + tests (8) | ✅ |
| **PRC-6** | Integraciones event-driven de costo + facade de lectura: `AverageCostingService` (costo promedio móvil Decimal/Money); `ProductCostProjectionHandler` consume `PURCHASE_STOCK_ENTRY_REGISTERED`/`PRODUCTION_OUTPUT_COSTED` → actualiza `product_cost` (idempotente vía `price_change_log`, atómico, emite `PRODUCT_COST_UPDATED` a outbox); `wire_pricing` (prioridad 50); `PricingReadFacade` (Decimal-first: `sale_price`/`unit_cost`/`average_cost`) como entrada canónica única para los 44 consumidores; migración **151** (`product_cost.tracked_quantity`); guardrail: Pricing no lee tablas legacy de precio/costo. *(El repunte físico de los 44 call-sites se ejecuta en el flip PRC-8, como en INV/PUR.)* | `domain/services/average_costing_service.py` + `application/pricing/{event_handlers,integrations,queries/pricing_read_facade}` + `migrations/151_*` + tests (26) | ✅ |
| **PRC-7** | UI/UX enterprise `frontend/desktop/modules/pricing/**` (born-clean, tema JUANIS, sin SQL): `PricingReadService` (read side: overview, listas, precios por producto/sucursal/lista, costos, historial; Decimal-only, LEFT JOIN a `products` canónico, `below_min` en Python); `view_models` es-MX (labels estado/tipo/método/fuente + `format_money`/`format_percentage`); `PricingPresenter`; `navigation` declarativa con permisos `PRICING_*` granulares; `routes`; 5 páginas presentation-only (Resumen/Listas/Precios/Costos/Historial) sobre `PageHeader`/`KPIBar`/`StandardTable`/`SearchInput`; guardrail UI-sin-DB | `frontend/desktop/modules/pricing/**` + `application/pricing/queries/pricing_read_service.py` + tests (23) + guardrail | ✅ |
| **PRC-8** | Eliminación de legacy: `core/services/pricing_service.py` reescrito de 158→60 líneas como **shim delegante** en `ProductPriceQueryService` (UUIDv7/Money, sin SQL de precio legacy, contrato dict preservado para `sales_service`; métodos de gestión muertos eliminados); DROP diferido `migrations/deferred/legacy_pricing_drop.py` (env-guard `PRICING_ALLOW_LEGACY_DROP=1`, NO registrado) de `listas_precio`/`precios_lista`/`precios_volumen`/`clientes_lista_precio`/`historial_precios` + triggers; guardrail ratchet anti-nuevos-lectores + allowlist; **desbloquea PROD-19 pasos 4-10** (los lectores de `productos.precio`/`costo` ya tienen destino canónico) | `pricing_legacy_removal_report.md` + shim + DROP diferido + tests (16) | ✅ |
| **PRC-9** | Validación final: **124 passed** (114 dominio/aplicación/integración + 10 guardrails), bootstrap limpio (149/150/151); auditorías UUIDv7 (`test_pricing_uses_uuidv7`), Money/Decimal sin REAL/float (`test_pricing_uses_money_decimal`), UI-sin-DB, sin lecturas legacy, ratchet, y `products` sin precio/costo (`test_product_master_does_not_own_pricing`) | `pricing_validation_report.md` + 3 auditorías | ✅ |

---

## Guardrails
```
tests/architecture/test_pricing_uses_money_decimal.py       (sin float/REAL)
tests/architecture/test_pricing_uses_uuidv7.py
tests/architecture/test_pricing_ui_has_no_database_access.py
tests/architecture/test_product_master_does_not_own_pricing.py  (refuerzo)
tests/architecture/test_pos_reads_price_from_pricing_context.py
```

## Definición de terminado
Un solo contexto Pricing/Costing (UUIDv7, Money/Decimal), resolución
volumen>cliente>lista>base con precio mínimo, costo promedio canónico, query
services que sirven a los 44 consumidores, backfill validado, UI enterprise, legacy
`pricing_service`/tablas de precio eliminadas, y **`productos` sin precio/costo** →
PROD-19 desbloqueado.
