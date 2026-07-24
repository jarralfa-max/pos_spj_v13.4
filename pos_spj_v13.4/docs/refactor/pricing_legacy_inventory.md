# PRC-0 — Inventario de legacy del bounded context de Pricing / Costing

Auditoría previa a la construcción del contexto canónico de **Precios y Costos**.
Su objetivo directo: dar a Productos un destino canónico para `precio`/`costo` y
**desbloquear el DROP de `productos`** (ver `products_legacy_removal_report.md`).
Sigue `SPJ_REFACTOR_SKILL.md` (REGLA CERO UUIDv7, Decimal-only, sin SQL en UI).

## 1. Dónde vive precio/costo hoy (legacy)

### 1.1 Columnas en el maestro legacy `productos`
| Columna | Concepto | Destino canónico |
| ------- | -------- | ---------------- |
| `precio` | Precio base de venta | `product_price` (lista BASE) |
| `precio_minimo_venta` / `precio_minimo` | Precio mínimo (protección) | `product_price.min_price` / `MarginPolicy` |
| `precio_compra` | Costo de compra | `product_cost.last_cost` |
| `costo` / `costo_promedio` | Costo / costo promedio | `product_cost.average_cost` |
| `margen_objetivo_pct` | Margen objetivo | `MarginPolicy.target_margin_pct` |

### 1.2 Tablas de precios legacy
| Tabla | Rol | Acción |
| ----- | --- | ------ |
| `listas_precio` | Listas de precio (descuento global, herencia) | REPLACE → `price_list` |
| `precios_lista` | Precio por (lista, producto) | REPLACE → `product_price` |
| `precios_volumen` | Precio por cantidad (kg ≥ 10 → especial) | REPLACE → `volume_price` |
| `clientes_lista_precio` | Cliente → lista | REPLACE → `customer_price_list` |
| `branch_products.precio_local` | Precio por sucursal | REPLACE → `product_price.branch_id` |
| `historial_precios` | Bitácora de cambios (REAL) | REPLACE → `price_change_log` (Decimal) |

### 1.3 Servicios / motores legacy
| Archivo | Problema | Acción |
| ------- | -------- | ------ |
| `core/services/pricing_service.py` (158) | `producto_id: int` (viola REGLA CERO), precios float, SQL sobre `productos.precio`/`precios_lista`/`precios_volumen` | **REWRITE** → `PricingResolutionService` canónico |
| `backend/application/procurement/use_cases/pricing_use_cases.py`, `backend/domain/procurement/pricing_policies.py` | Pricing de **compra** (Procurement) — distinto de precio de venta | **REUSE** (contexto Compras; alimenta `product_cost`) |
| `production_cost_ledger` | Costo real de producción | **REUSE** (alimenta `product_cost.average_cost`) |

## 2. Consumidores (44 archivos leen precio/costo)

POS/Ventas (precio de venta, precio mínimo), BI (rentabilidad usa costo), Compras
(costo), Fidelidad (precio para puntos), Tickets (precio), Delivery. Todos leen
`productos.precio`/`precio_compra` o `precios_lista` directamente. Se repuntan a
`ProductPriceQueryService` / `ProductCostQueryService` en PRC-5/6.

## 3. Reglas de negocio a preservar

- Prioridad de resolución: **volumen > lista de cliente > lista > precio base** (de
  `pricing_service.get_precio`).
- Precio mínimo de venta como protección (bloquea descuento por debajo).
- Descuento global por lista + herencia entre listas.
- Precio por sucursal (override).
- Costo promedio ponderado (de compras/producción).

## 4. Objetivo

Un solo contexto **Pricing/Costing** born-clean (UUIDv7, Decimal, Money VO) que:
- posea precio de venta (listas, volumen, sucursal, cliente) y costo (promedio,
  último, estándar);
- exponga `ProductPriceQueryService` / `ProductCostQueryService` para que los 44
  consumidores lean de ahí (no de `productos`);
- se respalde por backfill desde `productos`/`precios_lista`;
- desbloquee el DROP de `productos` (Productos deja de ser fuente de precio/costo).
