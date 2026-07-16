"""Wrapper legacy: Proveedores (CxP) es una página del módulo de Finanzas."""
from __future__ import annotations

from frontend.desktop.modules.finance.finance_routes import create_finance_view


class ModuloProveedores:
    def __new__(cls, container, parent=None):
        view = create_finance_view(container, parent)
        view.set_active_submodule("cxp")
        return view
