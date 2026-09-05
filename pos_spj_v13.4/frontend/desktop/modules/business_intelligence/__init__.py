"""Business Intelligence desktop module (§6/BI-23).

Not wired into `interfaz/menu_lateral.py`/`main_window.py`/
`core/app_container.py` yet — the legacy `INTELIGENCIA_BI` entry there still
points at `modulos/reportes_bi_v2.py::ModuloReportesBIv2`, which has 10 live
sections (ventas/inventario/compras/caja/clientes/proveedores/finanzas/
merma/reportes/configuracion) this module does not have parity with yet
(only "Resumen ejecutivo" has a real page, BI-24). Same coexistence pattern
already established for Pedidos y Delivery
(`frontend/desktop/modules/orders_delivery/orders_delivery_view.py`'s own
docstring) — swapping the live `_conectar("INTELIGENCIA_BI", ...)` line is a
cutover decision for once real parity exists, not something to do silently
as a side effect of building the skeleton.
"""
