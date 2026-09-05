# BI-30 — Reports (biblioteca, programados, exportaciones)

Estado: **DONE**, alcance limitado a exportaciones reales (ver
justificación de "programados" abajo)

## Alcance

§14/§30: biblioteca de reportes, reportes programados, exportaciones.

## Decisión central: reusar `BiExportService`, ya real y ya usado por el legacy

`modulos/reportes_bi_v2.py` ya tiene una pestaña "Reportes" completa que
llama `bi_dashboard_service.build_dashboard(filters).to_dict()` →
`bi_export_service.export_summary(payload, meta, ruta, fmt)` (xlsx/pdf/csv,
con fallback automático a CSV si `openpyxl`/`reportlab` no están instalados
— ya documentado en el propio servicio). BI-30 no reescribe esto: construye
la MISMA llamada a través del Design System nuevo en vez del legacy.

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `frontend/desktop/modules/business_intelligence/presenters/reports_presenter.py` | `ReportsPresenter` — `REPORT_CATALOG` (1 entrada real: "Resumen ejecutivo") + `generate()` que llama `BiDashboardService.build_dashboard()` real y `BiExportService.export_summary()` real. |
| `frontend/desktop/modules/business_intelligence/pages/reports_page.py` | `ReportsPage` — selector de reporte + selector de formato + botón "Exportar" → diálogo nativo de guardado (`QFileDialog`) → archivo real en disco. |
| `backend/application/analytics/permissions.py` (editado) | `AnalyticsPermissions.REPORTS_EXPORT` — reutiliza el código legacy plano ya registrado `"INTELIGENCIA_BI.exportar"` (§3/§64: una sola ruta canónica, no un permiso nuevo). |
| `business_intelligence_sidebar.py` (editado) | 13ª entrada de navegación, `bi_reports`, mapeada a `REPORTS_EXPORT`. |
| `business_intelligence_routes.py` (editado) | `bi_reports` ahora construye `ReportsPage` cuando hay `connection`. |

## Por qué "biblioteca" tiene solo 1 entrada

`BiExportService.export_summary()` solo sabe renderizar UN payload —
el del dashboard ejecutivo. Una "biblioteca" con más entradas (ej. "Reporte
de ventas", "Reporte de inventario") necesitaría que `BiExportService`
aprenda a exportar esos otros payloads primero — no inventado aquí sin ese
trabajo real hecho.

## Por qué "reportes programados" NO se construyó

No existe en todo el repositorio ninguna infraestructura de programación de
trabajos (cron-like, cola de jobs recurrentes, historial de ejecuciones) —
ni para BI ni para ningún otro módulo. Construir un scheduler completo desde
cero solo para soportar un tipo de reporte habría sido exactamente la
"infraestructura sin consumidor real" que esta transformación ha evitado en
cada fase anterior. Brecha documentada, no fabricada.

## Auditoría REGLA CERO

Sin identidad nueva — solo composición/exportación de datos ya validados.
N/A.

## Tests

`test_reports_presenter.py` (6: catálogo de 1 entrada, nombre de archivo por
defecto, reporte/formato desconocidos rechazados, y una exportación CSV
real contra una conexión sin esquema que confirma que se escribe un archivo
de verdad en disco), `test_reports_page.py` (4: construcción de selectores,
diálogo cancelado no hace nada, exportación real escribe un archivo,
ruteo). **10 tests nuevos, todos verdes** (122 en el paquete
`business_intelligence` completo).

## Pendiente

- Sin más entradas en la biblioteca hasta que `BiExportService` sepa
  renderizar otros payloads.
- Sin reportes programados — brecha honesta, no un placeholder.
- BI-31 audita responsive/touch/accessibility; BI-32 retira legacy
  confirmado sin consumidores.
