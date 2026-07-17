"""Wrapper legacy: Proveedores es el maestro canónico dentro de Finanzas.

Abre Finanzas en la página del maestro de proveedores (no hay menú independiente).
"""
from __future__ import annotations

from frontend.desktop.modules.finance.finance_routes import create_finance_view


class ModuloProveedores:
    def __new__(cls, container, parent=None):
        view = create_finance_view(container, parent)
        view.set_active_submodule("proveedores")
        return view
