"""Proveedores — el maestro de proveedores como página dentro de Finanzas.

El presentador de proveedores se compone en ``finance_routes`` (auditoría
F26); la página no recibe la conexión.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from frontend.desktop.modules.finance.suppliers.suppliers_view import SuppliersView


class SuppliersPage(QWidget):
    """Página de navegación de Finanzas que aloja el maestro de proveedores."""

    def __init__(self, finance_presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("suppliersFinancePage")
        self._loaded = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        supplier_presenter = finance_presenter.embedded_presenter("suppliers")
        self._view = None
        if supplier_presenter is None:
            message = QLabel("El maestro de proveedores no está disponible.", self)
            message.setProperty("role", "muted")
            layout.addWidget(message)
            return
        self._view = SuppliersView(supplier_presenter, self)
        layout.addWidget(self._view)

    def ensure_loaded(self) -> None:
        if not self._loaded and self._view is not None:
            self._view.ensure_loaded()
            self._loaded = True

    def reload(self) -> None:
        if self._view is not None:
            self._view.ensure_loaded()
