"""TarjetasFidelidadOverviewPage (LOY-25) — minimal landing page.

No card/template directory listing exists in the backend yet (LOY-16/17
only built single-entity lookups: `get`/`get_by_number`/`get_by_code`, no
`list_all()`) — this page stays a static welcome message rather than
fabricating counts it cannot honestly compute, unlike Fidelidad's own
overview page which DOES have real `list_active()` methods to draw from.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from frontend.desktop.themes.tokens import Spacing


class TarjetasFidelidadOverviewPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("tarjetasFidelidadOverviewPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)
        message = QLabel(
            "Usa \"Tarjetas\" para emitir/activar/bloquear una tarjeta, o "
            "\"Plantillas\" para crear y activar un diseño.", self)
        message.setWordWrap(True)
        layout.addWidget(message)
        layout.addStretch(1)

    def ensure_loaded(self) -> None:
        pass
