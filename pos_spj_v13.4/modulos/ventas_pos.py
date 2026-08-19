"""Wrapper legacy: módulo VENTAS_POS (decomposed).

La implementación vive en ``frontend/desktop/modules/sales_pos`` (bounded
context Sales/POS, POS-19). Igual que ``modulos/clientes_crm.py`` para
Customer Master/CRM: el desempaquetado del contenedor ocurre EN ESTE
archivo — ``frontend/desktop/modules/sales_pos/composition.py`` nunca
recibe el contenedor completo, solo una conexión, un contexto de sesión y
(específico de Ventas) un ``printer_service`` ya extraídos.

Este módulo es NUEVO, paralelo al legacy ``modulos/ventas.py``
(``_conectar("POS", ModuloVentas, ...)``) — NO lo reemplaza ni está
conectado a ``interfaz/main_window.py`` todavía. Ver
``docs/refactor/SALES-19_ui_decomposition.md`` para el razonamiento
completo y lo que falta para un swap-over real.
"""
from __future__ import annotations

from frontend.desktop.modules.sales_pos.composition import create_sales_pos_view


class ModuloVentasPos:
    """Factory-compatible: ``ModuloVentasPos(container)`` devuelve la vista
    decompuesta nueva."""

    def __new__(cls, container, parent=None):
        connection = getattr(container, "db", None) or getattr(container, "db_conn", None)
        session_context = getattr(container, "session", None)
        printer_service = getattr(container, "printer_service", None)
        return create_sales_pos_view(connection, session_context, printer_service, parent)
