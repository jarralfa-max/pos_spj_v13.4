# BI-23 — UI Foundations (routes, sidebar, Design System)

Estado: **DONE** (esqueleto navegable completo; no wireado en producción
todavía, coexistencia deliberada — ver abajo)

## Alcance

§6/§14/§89-90: crear `frontend/desktop/modules/business_intelligence/` con
routing, sidebar y Design System — sin lógica de negocio en la UI, sin
`QTableWidget`/`design_tokens` legacy/emojis.

## Investigación previa (resumen)

Antes de escribir código se investigó la convención real de módulos ya
migrados (`losses`, `orders_delivery`) porque **no existe una clase base
`ModuleSidebar` genérica** en el repo — cada módulo arma su propio
`<Módulo>SidebarWidget(QListWidget)` a partir de una tupla declarativa de
`NavEntry`. `orders_delivery` se usó como plantilla exacta (tiene rutas
reales wireadas, a diferencia de `losses` que aún es 100% placeholder).

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `frontend/desktop/modules/business_intelligence/navigation/business_intelligence_sidebar.py` | `BiNavEntry` + `BUSINESS_INTELLIGENCE_NAV` (12 secciones de nivel superior) + `visible_entries()`. |
| `frontend/desktop/modules/business_intelligence/widgets/business_intelligence_sidebar_widget.py` | `BusinessIntelligenceSidebarWidget(QListWidget)` — copia exacta de `OrdersDeliverySidebarWidget`. |
| `frontend/desktop/modules/business_intelligence/business_intelligence_view.py` | `BusinessIntelligenceView` — sidebar + `QStackedWidget`, sin `QTabWidget`. |
| `frontend/desktop/modules/business_intelligence/business_intelligence_routes.py` | `build_page()` — registro único de rutas; solo `bi_executive` tiene página real (BI-24), las otras 11 caen a `BusinessIntelligencePlaceholderPage`. |
| `frontend/desktop/modules/business_intelligence/pages/placeholder_page.py` | Página vacía honesta (`ViewState.EMPTY`, sin datos falsos) para secciones sin implementación todavía. |

## Las 12 secciones de nivel superior (y por qué esas y no las ~50 de §14)

§14 describe un árbol anidado (Ventas>Resumen/Tendencias/Productos/...).
BI-23 solo declara el **nivel superior**, mapeado 1:1 a un código granular
real de `AnalyticsPermissions` (BI-2) y respaldado por un backend real
(BI-4..21): Resumen ejecutivo, Ventas, Inventario, Compras, Producción,
Precios, Sucursales, Finanzas, Forecast, Decision Intelligence, Escenarios,
Alertas. Los sub-ítems anidados (Ventas>Tendencias, etc.) son trabajo de
BI-25 (Analytical Pages) cuando existan sub-páginas reales que colgar ahí —
declararlos ahora sin contenido habría sido la misma "infraestructura sin
consumidor" que esta transformación ha evitado en cada fase anterior.

## Por qué NO se wireó en `main_window.py`/`menu_lateral.py`

El botón `"INTELIGENCIA_BI"` ya existe y apunta a
`modulos/reportes_bi_v2.py::ModuloReportesBIv2` — **10 secciones en vivo**
(ventas/inventario/compras/caja/clientes/proveedores/finanzas/merma/
reportes/configuracion). Este módulo nuevo solo tiene 1 de 12 secciones con
contenido real (BI-24). Reemplazar la entrada en vivo ahora sería una
regresión visible para cualquier usuario que use hoy el dashboard BI.
Mismo criterio, mismas palabras, que `orders_delivery_view.py` ya documenta
para su propio módulo: coexiste como una ruta adicional hasta que exista
paridad real, el reemplazo de la línea `_conectar("INTELIGENCIA_BI", ...)`
es una decisión de corte explícita, no un efecto secundario de construir el
esqueleto. Un guardrail (`test_module_not_yet_wired_into_main_window`)
protege esta decisión de revertirse por accidente.

## Auditoría REGLA CERO

Sin identidad nueva — value objects de navegación puros. N/A.

## Tests

`test_business_intelligence_navigation.py` (7, dataclasses puros),
`test_business_intelligence_sidebar_widget.py` (5, instanciación real de
Qt bajo `QT_QPA_PLATFORM=offscreen`, ya configurado globalmente en
`tests/conftest.py`), `test_business_intelligence_routes.py` (3),
`tests/architecture/test_business_intelligence_ui_foundations.py` (6:
sidebar+stack sin QTabWidget, páginas sin SQL/repositories, sin
design_tokens/setStyleSheet/QTableWidget legacy, sin emojis, permisos
registrados, no wireado en main_window). **21 tests nuevos, todos verdes.**

## Pendiente

- BI-25 construye los sub-ítems anidados de cada sección con página real.
- La decisión de cutover (reemplazar `ModuloReportesBIv2`) espera a que
  exista paridad funcional completa — no es parte de esta transformación
  todavía.
