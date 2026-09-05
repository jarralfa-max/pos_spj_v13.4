# BI-25 — Analytical Pages

Estado: **DONE** (4 de 7 secciones nombradas por el master prompt tienen
página real; las otras 3 se documentan como gap honesto, no se fabrican)

## Alcance

§14: páginas reales para Ventas/Inventario/Compras/Producción/Precios/
Sucursales/Finanzas — las secciones que en BI-23 quedaron como placeholder.

## Decisión central: reusar `BiDashboardService.section_data()`, no construir SQL nuevo

`BiDashboardService` (BI-4) ya expone `section_data(section, filters)` —
un payload real `{section, title, kpis[], charts[], tables[]}` por pestaña
detallada ("FASE 8" en el propio código), que hoy renderiza
`modulos/reportes_bi_v2.py`. BI-25 no reconstruye esa lógica: un único
`AnalyticalSectionPresenter` genérico + `AnalyticalSectionPage` genérica
traducen ese payload (dicts "mini" — título/valor/unidad/ícono/variante, más
simples que el `KpiCard` del dashboard ejecutivo) a los DTOs canónicos
(`KPIDTO`/`ChartDataDTO`/`SectionTableDTO`+`StandardTable`), exactamente el
mismo rol que `ExecutiveDashboardPresenter` cumplió en BI-24 para el payload
completo.

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `frontend/desktop/modules/business_intelligence/presenters/analytical_section_presenter.py` | `AnalyticalSectionPresenter(connection, section_key)` — llama `BiDashboardService.section_data()` una vez (memoizado hasta `invalidate()`), traduce `kpis`/`charts`/`tables` vía `_map_mini_kpi`/`_map_section_chart`/`_map_table` (funciones puras, testeadas sin Qt). `SectionTableDTO` puentea una tabla del payload a `ColumnSpec`+filas de texto para `StandardTable`. |
| `frontend/desktop/modules/business_intelligence/pages/analytical_section_page.py` | `AnalyticalSectionPage` — genérica: `PageHeader` + botón Actualizar + `KPIBar` + N×`HtmlChartView` + M×(`QLabel` título + `StandardTable`), construidos perezosamente en el primer `refresh()` (las columnas de cada tabla se fijan una vez, igual que `cash_ledger_page.py` ya hace). |
| `business_intelligence_routes.py` (editado) | 4 nuevas rutas reales (`bi_sales`→`ventas`, `bi_inventory`→`inventario`, `bi_purchasing`→`compras`, `bi_finance`→`finanzas`) comparten el mismo builder `_build_analytical_section`, mapeado por `_SECTION_KEY_BY_PAGE_ID`. |

## Por qué solo 4 de 7 secciones nombradas por §14

`BiDashboardService` solo tiene builders reales para
`_section_ventas`/`_section_inventario`/`_section_compras`/`_section_finanzas`
(además de `merma`/`caja`/`clientes`/`proveedores`, sin entrada en el nuevo
menú de 12 secciones de BI-23). **No existe** `_section_produccion`/
`_section_precios`/`_section_sucursales` — esos tres dominios solo tienen
servicios de recomendación por producto/sucursal individual (BI-14
`PurchasePlanningService`, BI-15 `ProductionPlanningService`, BI-16
`PricingDecisionService`, BI-17 `BranchIntelligenceService`), diseñados para
alimentar el flujo de recomendaciones (BI-18 `BusinessRecommendation`), no
para listar un agregado tipo dashboard. Construir una página "Producción"
con una nueva agregación SQL inventada, sin mandato real del master prompt
más allá de "mostrar recomendaciones" (que es exactamente lo que hará BI-27),
habría sido la misma "infraestructura sin consumidor real" que esta
transformación ha evitado en cada fase. `bi_purchasing` sí tiene página real
porque `_section_compras` existe y ya cubre "gasto + proveedores" — la
brecha real de Compras es más recomendaciones (BI-27), no más KPIs.

`test_production_pricing_and_branches_stay_placeholders_even_with_a_connection`
protege esta decisión de revertirse por accidente (mismo patrón que
`test_module_not_yet_wired_into_main_window` de BI-23).

## Auditoría REGLA CERO

Sin identidad nueva — solo lectura/traducción. N/A.

## Tests

`test_analytical_section_presenter.py` (13: formateo, mapeo KPI/chart/tabla,
y las 4 secciones reales contra un `BiDashboardService` en vivo con conexión
SQLite en memoria sin esquema), `test_analytical_section_page.py` (5:
construcción + las 4 rutas reales, sin renderizar charts),
`test_business_intelligence_routes.py` (+1: Producción/Precios/Sucursales
siguen siendo placeholder incluso con conexión). **19 tests nuevos, todos
verdes** (53 en el paquete `business_intelligence` completo).

## Pendiente

- Sin filtros de UI (rango de fechas/sucursal) todavía — cada página usa
  `DashboardFilters()` (preset "month") tal como BI-24 lo hace hoy.
- Producción/Precios/Sucursales esperan a BI-27 (recomendaciones) o a que
  alguien decida construir un query service agregado real para ellas.
- BI-26 construye Forecast; BI-27 Decision Intelligence/Recomendaciones;
  BI-28 Alertas.
