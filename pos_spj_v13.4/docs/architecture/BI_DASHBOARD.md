# Módulo BI — Dashboard ejecutivo

Arquitectura limpia para el dashboard de Inteligencia de Negocio (CEO/gerencial),
alineada al skill `SPJ_REFACTOR_SKILL.md`: **cero SQL en UI**, identidad UUIDv7,
backend en inglés, textos visibles en español.

## Capas

```
UI (modulos/reportes_bi_v2.py, bi_charts.py)   ← sólo presenta el payload
        │  consume
        ▼
BiDashboardService (application/services)      ← KPIs, charts, alerts, insights,
        │  orquesta                               predicciones, permisos, caché
        ▼
BiDashboardQueryService (application/queries)  ← agrega métricas (periodo actual
        │  compone                                 y anterior) + bundle de charts
        ├── BiSalesQueryService        (ventas, top, categorías, métodos, horas)
        ├── BiInventoryQueryService    (valorizado, merma, stock crítico)
        ├── BiFinanceQueryService      (CxC, CxP, gastos, compras, proveedores)
        └── BiForecastQueryService     (predicción media móvil)
        │  SQL parametrizado (UUIDv7 TEXT)
        ▼
SQLite / (PostgreSQL futuro)
```

DTOs en `backend/application/dto/bi_dashboard_dto.py`:
`DashboardFilters`, `KpiCard`, `ChartData`, `HighlightCard`, `Alert`, `Insight`,
`Prediction`, `DashboardPayload`.

## Payload del dashboard (FASE 14)

```python
DashboardPayload(
  filters, kpis[], charts{}, highlights{}, alerts[], predictions{}, insights[],
  allowed_sections[],
)
```

## KPIs y fórmulas (FASE 4)

| KPI | Fórmula | Mejor |
|-----|---------|-------|
| Ventas netas | `SUM(ventas.total)` estado='completada' | ↑ |
| Utilidad neta | `ventas_netas − costo_ventas − gastos` | ↑ |
| Margen % | `utilidad_neta / ventas_netas * 100` | ↑ |
| Ticket promedio | `ventas_netas / ordenes` | ↑ |
| Órdenes | `COUNT(ventas)` completadas | ↑ |
| Inventario valorizado | `SUM(inventory_stock.quantity * costo_producto)` | – |
| CxC | `SUM(accounts_receivable.balance>0)` | ↓ |
| CxP | `SUM(accounts_payable.balance>0)` | ↓ |
| Merma % | `merma_valor / ventas_netas * 100` | ↓ |
| Rotación | `costo_ventas / inventario_valorizado` | ↑ |

Costo de ventas (COGS) usa el costo real capturado por línea
(`detalles_venta.costo_unitario_real`) con fallback a
`productos.costo / precio_compra / costo_promedio`.

Cada KpiCard incluye comparación vs periodo anterior (`delta_pct` / `delta_points`),
`direction` (up/down/flat), `semantic` (positive/negative/neutral), `tooltip`,
`drilldown` y `formula`.

## Filtros globales (FASE 3)

`DashboardFilters`: preset (today/yesterday/week/month/last_month/custom),
date_from/date_to, branch_id, channel, category, payment_method, customer_id,
supplier_id, product_type. Combinables y persistibles por sesión.

Aplicados hoy en el query layer: **fecha, sucursal, método de pago, cliente,
categoría** (EXISTS). Pendientes de columna de esquema: **canal de venta** y
**tipo de producto** (se aceptan en el DTO pero aún no filtran).

## Charts (FASE 5)

`sales_trend` (línea doble ventas/utilidad), `branch_sales` (barras),
`top_products` (barras horizontales), `categories` (barras),
`payment_methods` (dona), `peak_hours` (línea), `forecast` (real vs pronóstico),
`profitability` (margen por categoría). Render SVG offline (`bi_charts.py`), sin CDN.

## Alertas e insights (FASE 6)

Alertas: merma alta, caída de ventas, aumento de CxC, margen bajo pese a ventas,
compras sin correlación de ventas. Insights: sucursal líder, categoría de
oportunidad, producto estrella, método de pago dominante, lectura de rentabilidad.
Todo derivado de datos reales; sin texto genérico vacío.

## Permisos (FASE 12)

`BiDashboardService` recibe un `permission_checker(perm)->bool` cableado en
`app_container` a `SessionContext.tiene_permiso` (admin ⇒ todo; sin sesión activa
no bloquea). `allowed_sections` del payload gatea las pestañas: `resumen` siempre
visible; el resto según los códigos canónicos del catálogo
`INTELIGENCIA_BI.{ver_ventas, ver_inventario, ver_compras, ver_caja,
ver_clientes, ver_proveedores, ver_finanzas, ver_merma, exportar, configurar}`
(registrados en `core/security/permission_catalog.py`).

## Drill-down

Cada KpiCard lleva `drilldown` (sección destino). El renderer envuelve la tarjeta
en un enlace `spjdrill:<section>`; el web view usa una `QWebEnginePage` que
intercepta ese esquema (`acceptNavigationRequest`) y cambia a la pestaña
detallada correspondiente.

## Rendimiento (FASE 10)

Caché en memoria por firma de filtros (TTL configurable, 60s por defecto) en el
application service. `invalidate_cache()` para refresco.

## Pendiente (siguientes iteraciones)

- Pestañas detalladas por sección (Ventas/Inventario/Compras/Caja/Clientes/
  Proveedores/Finanzas/Merma/Reportes/Config) consumiendo el mismo query layer.
- KPI bar de 10 tarjetas + columna lateral de highlights/alertas/insights en la UI.
- Filtro de canal de venta y tipo de producto (requiere columnas/joins de delivery).
- Exportación ejecutiva (PDF/Excel) respetando filtros, usuario y rango.
- Cableado del `permission_checker` real desde la sesión.
