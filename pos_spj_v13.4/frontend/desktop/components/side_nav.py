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

    _BASE_LABEL_ROLE = Qt.UserRole + 20
    _BADGE_ROLE = Qt.UserRole + 21

    def add_section(self, label: str, icon=None, *, badge: int = 0) -> None:
        item = QListWidgetItem()
        item.setData(self._BASE_LABEL_ROLE, label)
        if icon is not None:
            item.setIcon(icon)
        self.addItem(item)
        self.set_badge(self.count() - 1, badge)

    def set_badge(self, row: int, count: int) -> None:
        item = self.item(row)
        if item is None or not bool(item.flags() & Qt.ItemIsEnabled):
            return
        count = max(0, int(count or 0))
        label = str(item.data(self._BASE_LABEL_ROLE) or item.text())
        item.setData(self._BADGE_ROLE, count)
        item.setText(f"{label}  ·  {count}" if count else label)
        item.setData(Qt.AccessibleTextRole,
                     f"{label}, {count} pendientes" if count else label)

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
