"""SuppliersView — container hosting the supplier list and opening the ficha.

Embeddable as a Finanzas page and openable contextually from Compras. Receives a
fully wired SupplierPresenter; never touches the database.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.modules.finance.suppliers.pages.supplier_detail_dialog import (
    SupplierDetailDialog,
)
from frontend.desktop.modules.finance.suppliers.pages.supplier_list_page import (
    SupplierListPage,
)


class SuppliersView(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("suppliersModule")
        self._presenter = presenter
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._list = SupplierListPage(presenter, self, on_open_detail=self.open_detail)
        layout.addWidget(self._list)

    def ensure_loaded(self) -> None:
        self._list.ensure_loaded()

    def open_detail(self, supplier_id: str) -> None:
        dialog = SupplierDetailDialog(self._presenter, supplier_id, self)
        dialog.exec_()
        self._list.reload()
