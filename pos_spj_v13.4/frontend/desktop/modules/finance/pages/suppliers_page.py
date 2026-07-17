"""Proveedores — the supplier master as a page inside Finanzas.

The single supplier master lives here (no standalone PROVEEDORES menu). It embeds
the self-contained SuppliersView, built from the finance connection.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.modules.finance.suppliers.supplier_routes import (
    build_supplier_presenter,
)
from frontend.desktop.modules.finance.suppliers.suppliers_view import SuppliersView


class SuppliersPage(QWidget):
    """Finance navigation page hosting the supplier master."""

    def __init__(self, finance_presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("suppliersFinancePage")
        self._loaded = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        supplier_presenter = build_supplier_presenter(
            finance_presenter.connection(), finance_presenter.session_context())
        self._view = SuppliersView(supplier_presenter, self)
        layout.addWidget(self._view)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self._view.ensure_loaded()
            self._loaded = True

    def reload(self) -> None:
        self._view.ensure_loaded()
