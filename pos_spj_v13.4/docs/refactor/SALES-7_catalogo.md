# SALES-7 — Catálogo (POS-7 del master prompt)

Fecha: 2026-08-16
Fase anterior: `SALES-6_application_layer.md`.

## Alcance ejecutado

Master prompt §67, fase POS-7: "QueryService. Search. Categories. Product cards. Tests."
Sección 14 del prompt exige un `ProductCatalogQueryService` que resuelva `stock_state` del
lado del servidor; sección 16 prohíbe explícitamente calcular ese estado en el widget a partir
de floats crudos.

## Hallazgo que definió el alcance real

Leí `core/services/sales/product_catalog_query_service.py` (el servicio legacy que
`modulos/ventas.py` ya usa) completo antes de diseñar nada. Dos hallazgos concretos:

1. **Su propia columna `stock_state` es código muerto**: `"stock_state": "ok"` — un literal
   hardcodeado, línea 93, nunca calculado a partir de existencia/mínimo real.
2. Esto explica exactamente por qué `ProductCard.__init__` (`modulos/ventas.py` 174-190,
   documentado en `sales_pos_layout_inventory.md`) calcula la clasificación de stock **dentro
   del widget** con floats crudos — el servicio que debería resolverlo nunca lo hizo. Es el
   anti-patrón textual que la sección 16 del master prompt prohíbe, confirmado por lectura
   directa, no asumido.

El servicio legacy además usa `float` de punta a punta (viola Decimal-only). Por las mismas
razones que justificaron reconstruir `Sale`/`SaleLine` desde cero en SALES-3 en vez de adaptar
el `Sale`/`Money` muerto de `domain/` raíz, esta fase construye un servicio nuevo y canónico en
vez de parchar el legacy — documentado explícitamente como coexistencia, no reemplazo (ver
"Lo que NO hizo" abajo).

## Entregables

**`backend/domain/sales/enums.py`** — `ProductStockState` (`AVAILABLE`/`LOW_STOCK`/
`CRITICAL_STOCK`/`OUT_OF_STOCK`/`NOT_SELLABLE`, exactamente los 5 de §16).

**`backend/domain/sales/policies/product_availability_policy.py`** — `ProductAvailabilityPolicy`:
- `classify(available_quantity, minimum_quantity, *, sellable_override=True)` — **porta el
  mismo umbral exacto** que hoy vive inline en el widget (agotado ≤0, crítico ≤mínimo, bajo
  ≤2×mínimo) a una política pura, Decimal-only, testeable — no se inventaron umbrales nuevos.
- `is_sellable(state, *, is_composite=False)` — mejora real que el widget nunca tuvo: un
  producto compuesto (`bundle_allowed`/`recipe_allowed`) sigue siendo vendible aunque su propia
  fila de stock esté en cero, porque se arma desde componentes al momento del cobro.

**`backend/application/sales/dto.py`** — `ProductCatalogEntryDTO`, exactamente el listado de
campos de salida de §14: `product_id`, `name`, `sku`, `barcode`, `unit`, `effective_price`,
`stock_state`, `available_quantity`, `image_reference`, `sellable`, `warnings`.

**`backend/application/sales/queries/catalog_query_service.py`** — `SalesCatalogQueryService`
(`search`/`get_categories`). Compone las mismas tablas canónicas que el servicio legacy ya usa
con éxito en producción (`products`, `product_price`, `price_list`, `product_categories`,
`inventory_replenishment_rule`, `product_images`, `product_barcodes`, `inventory_balances`) —
verificadas contra el esquema real de Productos/Pricing/Inventario antes de escribir el SQL
(investigación previa, no adivinado) — pero: dinero/cantidad como `Decimal` (nunca `float`),
`stock_state`/`sellable` resueltos vía `ProductAvailabilityPolicy` (nunca un placeholder),
búsqueda por nombre/SKU exacto/código de barras (mismo comportamiento que el legacy).

**Búsqueda (§15)**: implementada como capacidad del `search()` del QueryService (nombre
parcial, SKU exacto, código de barras exacto), no como un `ProductSearchController` de PyQt con
debounce — ese es un artefacto de UI (`frontend/desktop/modules/sales_pos/catalog/
product_search_bar.py` en la arquitectura objetivo del prompt, §8.1), y esta pipeline
(SALES-2..7) ha construido consistentemente solo las capas backend (dominio/aplicación/
infraestructura); la decomposición de UI es explícitamente POS-19 en la propia lista de fases
del prompt. Documentado como alcance diferido, no fabricado aquí.

**Tests** (17 nuevos, todos verdes en la primera corrida real — la investigación previa de
esquema evitó ciclos de depuración; 188 en total en toda la suite SALES-0..7, sin regresiones):
`tests/unit/test_sales_catalog.py` — 9 para la política (los 4 umbrales exactos + override +
la mejora de sellability para compuestos) + 8 para el QueryService, construido contra esquema
**real** de Productos/Pricing/Inventario (`create_products_schema`/`create_pricing_schema`/
`create_inventory_schema` llamados directamente, no un fixture aproximado a mano) — incluye
verificación explícita de que `stock_state` ya no es el placeholder `"ok"` del legacy, que el
Decimal se preserva de punta a punta, que un producto compuesto en cero sigue siendo vendible,
y que `available_quantity` está correctamente aislado por sucursal (una fila de inventario en
otra sucursal nunca se filtra).

## Lo que esta fase NO hizo (honesto, no fabricado)

- **No se tocó `core/services/sales/product_catalog_query_service.py`** ni
  `modulos/ventas.py::ProductCard` — el servicio legacy con su `stock_state` muerto y el widget
  con su clasificación inline siguen operando exactamente igual en producción. Esta fase deja
  el reemplazo listo, no lo conecta — mismo patrón que cada fase anterior (SALES-3 el agregado,
  SALES-6 los casos de uso).
- **Sin `ProductSearchController` de PyQt ni debounce de UI** — ver razonamiento arriba, es
  trabajo de POS-19.
- **`warnings` solo cubre el caso de stock bajo/crítico** — no incluye advertencias de otras
  fuentes (precio no configurado, producto sin categoría, etc.); ampliar la lista de
  advertencias posibles queda abierto para cuando exista un consumidor real.
- **No se importan Precios/Promociones/Cupones** — `effective_price` es el precio base de
  `product_price` (lista `BASE`), sin evaluar promociones/precios por sucursal específica más
  allá de branch_id=''. Coordinación real de Pricing (§24, evaluación de beneficios) es una
  fase posterior explícita del propio prompt (no POS-7).

## Siguiente fase

El master prompt continúa con POS-8 (Carrito: Add, Update, Remove, Totals, Tests) — gran parte
de esto ya existe desde SALES-3/SALES-6 (`Sale.add_line`/`update_line_quantity`/`remove_line`,
`AddSaleLineUseCase`/etc.), así que esa fase probablemente sea de consolidación/gap-filling más
que construcción desde cero. Confirmar con el usuario antes de asumir alcance u orden.
