"""Accessible persistent sidebar for the Meat Processing workspace. Mirrors
frontend/desktop/modules/losses/widgets/losses_sidebar_widget.py.
"""

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem

from frontend.desktop.modules.meat_processing.navigation.meat_processing_sidebar import (
    visible_entries,
)
from frontend.desktop.themes.tokens import IconSizes, SidebarMetrics


class MeatProcessingSidebarWidget(QListWidget):
    route_requested = pyqtSignal(str)

    _TITLE_ROLE = Qt.UserRole + 1

    def __init__(self, *, has_permission, badges=None, has_feature=None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("moduleSidebar")
        self.setProperty("role", "nav")
        self.setAccessibleName("Navegación del módulo de procesamiento cárnico")
        self.setAccessibleDescription(
            "Selecciona una sección de Procesamiento Cárnico. Usa las flechas para recorrerla."
        )
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setUniformItemSizes(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMinimumWidth(SidebarMetrics.WIDTH - 30)
        self.setMaximumWidth(SidebarMetrics.WIDTH + 20)
        self._collapsed = False
        for entry, badge in visible_entries(has_permission, badges, has_feature):
            title = entry.title if badge is None else f"{entry.title} ({max(0, int(badge))})"
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, entry.page_id)
            item.setData(self._TITLE_ROLE, title)
            item.setToolTip(entry.tooltip)
            item.setData(Qt.AccessibleDescriptionRole, entry.tooltip)
            accessible = entry.title
            if badge is not None:
                accessible = f"{entry.title}, {max(0, int(badge))} pendientes"
            item.setData(Qt.AccessibleTextRole, accessible)
            item.setSizeHint(item.sizeHint().expandedTo(QSize(0, SidebarMetrics.ITEM_HEIGHT)))
            self.addItem(item)
        self.currentItemChanged.connect(self._emit_route)
        if self.count():
            self.setCurrentRow(0)

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = bool(collapsed)
        if self._collapsed:
            self.setFixedWidth(IconSizes.XL + 24)
        else:
            self.setMinimumWidth(SidebarMetrics.WIDTH - 30)
            self.setMaximumWidth(SidebarMetrics.WIDTH + 20)
        for row in range(self.count()):
            item = self.item(row)
            title = str(item.data(self._TITLE_ROLE) or "")
            item.setText(title[:1] if self._collapsed else title)
            item.setTextAlignment(Qt.AlignCenter if self._collapsed else Qt.AlignLeft)

    def _emit_route(self, current, _previous) -> None:
        if current is not None:
            self.route_requested.emit(str(current.data(Qt.UserRole)))
