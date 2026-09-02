# ORD-4 — Sidebar y navegación (Pedidos y Delivery)

Fecha: 2026-08-29. Alcance: master prompt §68 (single "PEDIDOS Y DELIVERY" sidebar entry).

## Qué se construyó

`frontend/desktop/modules/orders_delivery/` — skeleton navegable, mirror exacto de
`frontend/desktop/modules/losses/`: `navigation/orders_delivery_sidebar.py` (23 entradas
declarativas permission-gated), `widgets/orders_delivery_sidebar_widget.py`,
`orders_delivery_routes.py` (todas resuelven a `OrdersDeliveryPlaceholderPage` por ahora),
`orders_delivery_view.py` (contenedor sidebar+stack responsive).

`backend/application/orders_delivery/queries/order_badge_query_service.py` —
`OrdersDeliveryBadgeQueryService`, consulta las tablas NUEVAS (`customer_orders`, ORD-3),
no la legacy `delivery_orders` (`core/services/order_badge_service.py` sigue sirviendo el
sidebar legacy). Degrada a 0 de forma defensiva si falta la tabla — mismo criterio que su
contraparte legacy.

Dos permisos nuevos agregados a `OrdersDeliveryPermissions` (`ALERTS_VIEW`/
`ANALYTICS_VIEW`, `DELIVERY.alertas.ver`/`DELIVERY.analisis.ver`) — el catálogo de ORD-1 no
cubría "Alertas"/"Análisis" del sidebar; mismo patrón que `PRODUCCION.alertas.ver`/
`PRODUCCION.analisis.ver`.

## Explícitamente NO hecho

**No se registró en `interfaz/menu_lateral.py`/`main_window.py`/`core/app_container.py`.**
Cablear la navegación nueva en el shell legacy real es una decisión separada y de mayor
alcance (mismo patrón que Configuración "(Nuevo)" en `module_relocation_map.md`) — no
tomada aquí sin autorización explícita. `modulos/delivery.py` sigue siendo la única UI de
Delivery que el usuario ve hoy.

## Tests

11 tests (`tests/unit/test_orders_delivery_navigation.py`): unicidad de `page_id`,
permisos registrados, filtrado por permiso, badges, cobertura de rutas, degradación a
cero del badge service. Verificado además con una construcción PyQt real
(`QT_QPA_PLATFORM=offscreen`): 23 entradas de sidebar, primera ruta auto-seleccionada,
página placeholder renderiza.

## Pendiente

- Páginas reales reemplazan los placeholders conforme cada fase funcional se construye
  (ORD-5+).
- Decisión de cutover/registro en el shell real: pendiente, requiere autorización aparte.
