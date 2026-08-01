"""DirectPurchaseView — container hosting the direct-purchase capture page.

Embeddable inside Compras. Receives a fully wired DirectPurchasePresenter; never
touches the database.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.modules.purchasing.pages.direct_purchase_create_page import DirectPurchaseCreatePage
from frontend.desktop.modules.purchasing.pages.direct_purchase_history_page import DirectPurchaseHistoryPage


class DirectPurchaseCreateView(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("directPurchaseCreateModule")
        self._presenter = presenter
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._page = DirectPurchaseCreatePage(presenter, self)
        layout.addWidget(self._page)

    def ensure_loaded(self) -> None:
        return None

    def start_create(self) -> None:
        self._page.start_create()

    def start_from_requisition(self, detail: dict) -> None:
        self._page.start_from_requisition(detail)


class DirectPurchaseHistoryView(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("directPurchaseHistoryModule")
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self._page = DirectPurchaseHistoryPage(presenter, self)
        layout.addWidget(self._page)

    def ensure_loaded(self): self._page.ensure_loaded()
    def reload(self): self._page.reload()
