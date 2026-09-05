# BI-24 — Executive Dashboard

Estado: **DONE** (página real, conectada al `BiDashboardService` real de
BI-4; sin refresco automático/exportación todavía — fuera de alcance)

## Alcance

§13: máximo 6 KPIs primarios + gráficas. La primera página real del módulo
nuevo (`frontend/desktop/modules/business_intelligence/`, BI-23).

## Decisión central: reusar `BiDashboardService`, no reconstruirlo

BI-0 ya encontró que `BiDashboardService` (movido a
`backend/application/analytics/` en BI-4) es "ya limpio" — cero SQL en UI,
arquitectura documentada en `docs/architecture/BI_DASHBOARD.md`. BI-24 no
reescribe esa lógica: `ExecutiveDashboardPresenter` solo **traduce** su
salida (`KpiCard`/`ChartData`, dicts planos pre-Design-System) a los DTOs
canónicos que los componentes nuevos esperan (`KPIDTO`/`ChartDataDTO`).

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `frontend/desktop/modules/business_intelligence/presenters/executive_dashboard_presenter.py` | `ExecutiveDashboardPresenter` — construye `BiDashboardQueryService`+`BiDashboardService` reales sobre la conexión recibida; `kpi_cards()`/`charts()` traducen la salida vía `_map_kpi`/`_map_chart` (funciones puras, testeadas exactamente sin necesitar Qt). Capa a 6 KPIs (§13). |
| `frontend/desktop/modules/business_intelligence/pages/executive_dashboard_page.py` | `ExecutiveDashboardPage` — copia exacta de `OrdersAnalyticsPage`: `PageHeader` + botón Actualizar + `KPIBar` + N×`HtmlChartView`. |

## Bug real encontrado y corregido durante esta fase

`_map_chart` originalmente forzaba `float(v)` sobre cada valor de serie.
La gráfica "forecast" de `BiDashboardService` (`r["forecast"]["real"]`)
legítimamente trae `None` para fechas futuras (sin dato real observado
todavía) — `float(None)` explota. El propio `ChartSeriesDTO.data` está
tipado `tuple[float | None, ...]` precisamente para este caso (un hueco es
un dato válido, no un error). Se corrigió preservando `None` en vez de
forzar el cast — encontrado por el test
`test_presenter_degrades_gracefully_against_a_bare_connection`, que
efectivamente ejercita las 8 gráficas reales del payload (no solo las que
tienen datos "felices").

## Gotcha de entorno confirmado (no nuevo, ya documentado en el repo)

`HtmlChartView` (QtWebEngine) cuelga/crashea con
`Windows fatal exception: access violation` bajo la plataforma Qt
`offscreen` de este entorno de test — el mismo problema que
`tests/integration/inventory/test_inventory_ui_presenter.py::TestPagesSmoke`
ya documenta y evita excluyendo `InventoryAnalyticsPage` de sus pruebas de
construcción+refresco. `test_executive_dashboard_page.py` sigue el mismo
patrón: nunca llama `.ensure_loaded()`/`.refresh()` sobre una página real
(que renderizaría charts de verdad); la ruta de datos completa (qué le
llegaría a esos widgets) ya está cubierta exhaustivamente vía el presenter.

## Validación real contra un `BiDashboardService` en vivo

Los tests corren `ExecutiveDashboardPresenter` contra una conexión SQLite
real (en memoria, sin esquema) y confirman que las 10 KPIs + 8 gráficas que
`BiDashboardService` ya genera hoy (verificado manualmente antes de escribir
el test) se traducen sin excepción — no es un mock del backend, es el
backend real degradando con tablas ausentes tal como ya lo hace en
producción cuando faltan datos.

## Auditoría REGLA CERO

Sin identidad nueva — solo lectura/traducción. N/A.

## Tests

`test_executive_dashboard_presenter.py` (11: formateo de valores/tendencia,
mapeo KPI→variant, mapeo chart→ChartType incluida la gráfica vacía, y 2
contra un `BiDashboardService` real), `test_executive_dashboard_page.py`
(2, construcción + routing, sin renderizar charts). **13 tests nuevos,
todos verdes.**

## Pendiente

- Sin refresco automático (polling/eventos) ni exportación desde esta
  página — el botón "Actualizar" es manual, igual que
  `OrdersAnalyticsPage`.
- `KpiCard.drilldown`/`formula` (ya presentes en el payload real) no se
  usan todavía — el "¿Cómo se calcula?" de §12 se conecta cuando exista
  un diálogo de lineage real (ninguna página del repo lo tiene todavía).
- BI-25 construye el resto de las 11 secciones con contenido real.
