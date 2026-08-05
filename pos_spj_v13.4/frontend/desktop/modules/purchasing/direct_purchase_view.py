"""Direct-purchase view containers: separate create and history workspaces.

Embeddable inside Compras. Each receives a fully wired DirectPurchasePresenter;
neither touches the database. Creation and history are intentionally separate
screens (never combined) so a saved draft/pending authorization from one
purchase can't be confused with the document currently being captured.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.modules.purchasing.pages.direct_purchase_create_page import (
    DirectPurchaseCreatePage,
)
from frontend.desktop.modules.purchasing.pages.direct_purchase_history_page import (
    DirectPurchaseHistoryPage,
)


class DirectPurchaseCreateView(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("directPurchaseCreateModule")
        self._presenter = presenter
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._page = DirectPurchaseCreatePage(presenter, self)
        layout.addWidget(self._page)

    def start_create(self) -> None:
        self._page.start_create()

    def start_from_requisition(self, detail: dict) -> None:
        self._page.start_from_requisition(detail)


class DirectPurchaseHistoryView(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("directPurchaseHistoryModule")
        self._presenter = presenter
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._page = DirectPurchaseHistoryPage(presenter, self)
        layout.addWidget(self._page)

    def ensure_loaded(self) -> None:
        self._page.ensure_loaded()

    def reload(self) -> None:
        self._page.reload()
