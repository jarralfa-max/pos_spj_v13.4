"""DirectPurchaseView — container hosting the direct-purchase capture page.

Embeddable inside Compras. Receives a fully wired DirectPurchasePresenter; never
touches the database.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.modules.purchasing.pages.direct_purchase_page import (
    DirectPurchasePage,
)


class DirectPurchaseView(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("directPurchaseModule")
        self._presenter = presenter
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._page = DirectPurchasePage(presenter, self)
        layout.addWidget(self._page)

    def ensure_loaded(self) -> None:
        self._page.ensure_loaded()

    def reload(self) -> None:
        self._page.reload()
