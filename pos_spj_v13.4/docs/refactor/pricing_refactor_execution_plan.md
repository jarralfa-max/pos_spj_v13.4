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
| PRC-5 | Backfill: migración `productos`/`precios_lista`/`precios_volumen`/`branch_products.precio_local` → `product_price`/`volume_price`/`product_cost` (Decimal, idempotente) | migración de backfill + tests | ⏳ |
| PRC-6 | Integraciones: repuntar POS/Ventas/BI/Compras/Fidelidad/Tickets a `ProductPriceQueryService`/`ProductCostQueryService`; costo desde compras/producción (evento) | event_handlers + queries + tests | ⏳ |
| PRC-7 | UI/UX enterprise: `frontend/desktop/modules/pricing/**` (listas, precios por producto/sucursal/canal, costos, historial), tema JUANIS, sin SQL en UI | frontend + guardrails | ⏳ |
| PRC-8 | Eliminación de legacy: reescribir/borrar `pricing_service.py`, DROP diferido de `listas_precio`/`precios_lista`/`precios_volumen`/`historial_precios`; **desbloquea PROD-19 pasos 4-10** | `pricing_legacy_removal_report.md` + DROP diferido | ⏳ |
| PRC-9 | Validación final: suites dominio/aplicación/integración/UI/arquitectura + bootstrap limpio + auditorías (UUIDv7, Decimal/Money, sin precio en Product) | reporte de validación | ⏳ |

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
