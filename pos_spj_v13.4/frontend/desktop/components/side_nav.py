"""SideNav — barra de navegación lateral enterprise (DS).

Lista vertical de secciones (icono opcional + etiqueta) que emite ``navigated(int)``
al cambiar la selección. Diseñada para acompañar un ``QStackedWidget``: el índice de
la sección coincide con el índice de la página apilada. Sólo presentación —
estilizable por QSS vía ``objectName`` (``sideNav`` / ítems).
"""

from __future__ import annotations

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import QListWidget, QListWidgetItem


class SideNav(QListWidget):
    #: Emitido con el índice de la sección seleccionada.
    navigated = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sideNav")
        self.setFocusPolicy(self.focusPolicy())
        self.setUniformItemSizes(True)
        self.setIconSize(QSize(18, 18))
        self.setMinimumWidth(180)
        self.setMaximumWidth(240)
        self.currentRowChanged.connect(self._on_row_changed)

    def add_section(self, label: str, icon=None) -> None:
        item = QListWidgetItem(label)
        if icon is not None:
            item.setIcon(icon)
        self.addItem(item)

    def add_group(self, label: str) -> None:
        """Add a non-interactive semantic heading to a module sidebar."""
        item = QListWidgetItem(label)
        item.setFlags(Qt.NoItemFlags)
        item.setData(Qt.AccessibleTextRole, label)
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        self.addItem(item)

    def _on_row_changed(self, row: int) -> None:
        if row >= 0:
            self.navigated.emit(row)

    def select(self, index: int) -> None:
        if 0 <= index < self.count():
            self.setCurrentRow(index)
