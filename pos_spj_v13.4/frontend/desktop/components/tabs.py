"""Keyboard-accessible tabs with overflow buttons and shared density."""

from PyQt5.QtWidgets import QTabBar, QTabWidget

from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import density_metrics


class TabBar(QTabBar):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("standardTabBar")
        self.setUsesScrollButtons(True)
        self.setExpanding(False)
        self.setAccessibleName("Pestañas")
        ThemeManager.instance().density_changed.connect(self._density_changed)

    def tabSizeHint(self, index):
        size = super().tabSizeHint(index)
        size.setHeight(max(size.height(), density_metrics().tab_height))
        return size

    def _density_changed(self, _density):
        self.updateGeometry()
        self.update()


class Tabs(QTabWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("standardTabs")
        self.setTabBar(TabBar(self))
        self.setUsesScrollButtons(True)
