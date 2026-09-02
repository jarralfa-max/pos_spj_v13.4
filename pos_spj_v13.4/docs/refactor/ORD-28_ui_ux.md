# ORD-28 — UI/UX: Sidebar / Páginas / Diálogos / Tema JUANIS / Responsive / Accesibilidad

Fecha: 2026-09-01. Alcance: master prompt ORD-28 ("1. Sidebar. 2. Páginas. 3. Diálogos.
4. Tema JUANIS. 5. Responsive. 6. Accesibilidad. 7. Tests."). Trabajo genuino de frontend
PyQt5 de **escritorio** — distinto de la PWA web de ORD-25.

## Contexto: 23 páginas, todas placeholder desde ORD-4

`frontend/desktop/modules/orders_delivery/orders_delivery_routes.py::build_page()` resolvía
CUALQUIER `page_id` de los 23 del sidebar (ORD-4) a la misma
`OrdersDeliveryPlaceholderPage`. Construir las 23 a nivel de producción completo
excedería por mucho el alcance razonable de una sola fase — se aplicó el mismo criterio de
alcance de cada fase anterior: un subconjunto REAL, bien probado, que demuestra el patrón
completo funcionando contra el backend real, con el resto documentado como pendiente
honesto.

## Qué se construyó (3 de 23 páginas + 1 diálogo, reales)

- **Resumen** (`orders_overview`) — `OrdersOverviewPage` + `OrdersOverviewPresenter`: KPI
  bar alimentada por `OrdersDeliveryAnalyticsQueryService.kpi_summary()` (ORD-27) +
  `OrdersDeliveryBadgeQueryService.get_badge_counts()` (ORD-4, ahora con los dos
  placeholders corregidos en ORD-27).
- **Todos los pedidos** (`orders_all`) — `OrdersListPage` (subclase real de la canónica
  `WorklistPage`: búsqueda, filtro por estado, tabla, paginación) + `OrdersListPresenter`
  (SQL directo de solo lectura contra `customer_orders`, mismo criterio de
  `OrdersDeliveryAnalyticsQueryService`). También aloja el botón "Nuevo pedido" en su
  encabezado (mismo patrón exacto que `ExpensesPage` de Finanzas: el diálogo se abre desde
  la página de lista, no desde una página dedicada separada).
- **Análisis** (`orders_analytics`) — `OrdersAnalyticsPage` + `OrdersAnalyticsPresenter`:
  KPI bar + 2 `HtmlChartView` (repartidores, SLA), usando el pipeline real
  `ChartDataDTO`/ECharts ya establecido por `LossAnalyticsPage`. **Esto cierra el gap de
  "Charts" que ORD-27 dejó deliberadamente abierto** (un query service no puede renderizar
  un widget; esta fase sí construye el widget real).
- **Diálogo "Nuevo pedido"** (`NewOrderDialog`) — usa el `FormDialog` canónico
  (`frontend.desktop.components.dialogs`), captura canal/modalidad/contacto/una línea, y
  delega en el REAL `CreateCustomerOrderUseCase` vía `OrdersListPresenter.create_order()`.

Las ~20 páginas restantes (Preparación, Ajustes de peso, Rutas, Liquidaciones, etc.) siguen
como `OrdersDeliveryPlaceholderPage` — gap documentado, no silencioso.

## Tema JUANIS / Responsive / Accesibilidad — reusados, no reinventados

Este proyecto YA tiene un sistema de diseño maduro
(`frontend/desktop/components/`: `KPIBar`, `HtmlChartView`, `PageHeader`, `WorklistPage`,
`StandardTable`, `FormDialog`, inputs especializados) usado por Finanzas/RRHH/Compras/
Losses/Cash Register. Las 3 páginas y el diálogo de esta fase usan ÚNICAMENTE esos
componentes canónicos — ningún color ni layout inline nuevo. Responsive y accesibilidad
básica ya venían resueltos a nivel de módulo desde ORD-4
(`OrdersDeliveryView.apply_responsive_layout()`, `setAccessibleName/Description`) y a
nivel de componente (`HtmlChartView` degrada a una tabla accesible si `QtWebEngine` no
está disponible — nunca un gráfico en blanco). Se agregó `setAccessibleName/Description`
a las 3 páginas nuevas para consistencia.

## Hallazgo real: un bug de crash reproducible en la suite de pruebas headless

Al probar el camino de error de `OrdersOverviewPage.refresh()` (un `QMessageBox.warning()`
real disparado por un presenter roto), pytest terminó con **access violation / segmentation
fault** en Windows bajo Qt headless (`QT_QPA_PLATFORM=offscreen`) — no un fallo de
aserción, un crash del proceso. Ya existía precedente exacto de este problema en
`tests/unit/test_transfers_ui_workspace.py`: la solución establecida es
`monkeypatch.setattr(page_module, "QMessageBox", FakeMessageBox)` — nunca invocar el
`QMessageBox` real en una prueba automatizada, sin importar la plataforma. Aplicado aquí;
confirmado que corrige el crash.

## Wiring de `build_page()`

`build_page(page_id, connection=None, *, branch_id=None, actor_user_id=None)` — con
conexión real, las 3 rutas cableadas devuelven la página real; sin conexión (el default,
igual que cada llamador/prueba existente de ORD-4), se preserva EXACTAMENTE el
comportamiento de placeholder original. `OrdersDeliveryView` gana los mismos parámetros
opcionales (`connection`/`branch_id`/`actor_user_id`), sin romper su firma existente.

## Tests

10 tests nuevos de integración headless (`tests/integration/test_orders_delivery_ui_pages.py`,
construcción real con `QApplication` + SQLite real): Resumen renderiza KPIs reales y nunca
truena con un presenter roto, Todos los pedidos lista/filtra pedidos reales y crea un
pedido real vía el diálogo, Análisis renderiza KPIs+gráficos sin crashear, el diálogo
produce el shape correcto para el caso de uso, y `build_page()` cablea las 3 rutas reales
sin romper el comportamiento placeholder-only cuando no hay conexión. Suite combinada
`orders_delivery` + `logistics`: **413/413 pasando**.

## Pendiente

- ~20 páginas restantes del sidebar (siguen como placeholder).
- Selección real de producto en "Nuevo pedido" (`ProductSearchBox` necesita un
  `SearchProvider` real contra el catálogo de productos — no construido aquí).
- Endpoint de ubicación GPS del repartidor (ya señalado en ORD-25).
- ORD-29 (eliminación de legacy) — requiere confirmación explícita del usuario antes de
  cualquier borrado, dado el alcance destructivo (ver `docs/refactor/
  orders_delivery_legacy_inventory.md` §75.17: "ninguna clasificación aquí es definitiva
  sin confirmar cero-consumidores antes de cualquier DELETE").
