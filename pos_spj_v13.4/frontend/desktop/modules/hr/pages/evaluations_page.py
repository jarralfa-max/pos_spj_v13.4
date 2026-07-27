"""Canonical HR evaluations page shell."""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import EmptyState, Icons, PageHeader
from frontend.desktop.themes import DesktopSpacing


class HREvaluationsPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG)
        layout.setSpacing(DesktopSpacing.MD)
        layout.addWidget(
            PageHeader(
                title="Evaluaciones",
                subtitle="Seguimiento de desempeño preparado para la fase canónica correspondiente.",
                icon=Icons.HR,
                parent=self,
            )
        )
        layout.addWidget(
            EmptyState(
                "Evaluaciones no disponibles todavía",
                "La funcionalidad se habilitará cuando el bounded context publique sus use cases.",
                self,
            )
        )
        layout.addStretch(1)
