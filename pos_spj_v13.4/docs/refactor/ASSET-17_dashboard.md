# ASSET-17 — Dashboard (Activos / EAM)

Ejecutado: 2026-09-02. §91-92 del prompt maestro.

## Qué se construyó

`frontend/desktop/modules/assets/pages/overview_page.py` — `AssetsOverviewPage`, ruta `assets.overview`. `reload()` llama a `presenter.dashboard()` (que a su vez llama a `AssetDashboardQueryService.kpis()`, ASSET-14) y renderiza exactamente lo que regresa — **"la UI no calcula KPI" (§91) se respeta literalmente**: no hay una sola suma, filtro o cálculo de negocio en este archivo.

**Solo se muestran los 5 KPIs que el backend realmente calcula hoy** (total de activos, disponibles, en mantenimiento, fuera de servicio, pendientes de baja) — no los 6 que sugiere §91 ("Valor de adquisición", "Costo mantenimiento del periodo"), porque esos requieren una proyección financiera de solo lectura (`AssetFinancialProjectionQueryService`) que esta pipeline no ha construido todavía (§63, listado como pendiente desde ASSET-14). Mostrar un número inventado habría sido peor que mostrar menos números reales.

Barra de alertas (`_AlertsBar`, mismo patrón que `customers_crm`'s propia barra): se activa cuando `out_of_service` o `disposal_pending` son mayores que cero — de nuevo, decisiones que la página ya recibe hechas del DTO, no que calcula.

## Tests

`tests/unit/assets/test_assets_ui_pages.py::TestAssetsOverviewPage` — renderiza KPIs desde un `AssetDashboardQueryService` falso, y muestra estado de error (sin marcar `_loaded`) si el QueryService lanza una excepción.

## Siguiente fase

ASSET-18 — Directorio y detalle (construida en la misma sesión, ver doc propio).
