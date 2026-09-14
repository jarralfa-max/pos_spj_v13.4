"""Shared action/filter rows with native Qt overflow and keyboard navigation."""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QLabel, QToolBar

from frontend.desktop.components.buttons import GhostButton


class Toolbar(QToolBar):
    def __init__(self, parent=None, *, title="Acciones"):
        super().__init__(title, parent)
        self.setObjectName("standardToolbar")
        self.setAccessibleName(title)
        self.setMovable(False)
        self.setFloatable(False)
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

    def add_widget(self, widget):
        return self.addWidget(widget)


class FilterBar(Toolbar):
    def __init__(self, parent=None):
        super().__init__(parent, title="Filtros")
        self.setObjectName("filterBar")


class ContextBar(Toolbar):
    def __init__(self, parent=None):
        super().__init__(parent, title="Contexto de la página")
        self.setObjectName("contextBar")

    def set_context(self, values):
        self.clear()
        for index, (label, value) in enumerate(values.items()):
            if index:
                self.addSeparator()
            self.addWidget(QLabel(f"{label}: {value}", self))


class Breadcrumbs(Toolbar):
    route_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent, title="Ruta actual")
        self.setObjectName("breadcrumbs")

    def set_items(self, items):
        """Items are (Spanish label, route); empty routes are current labels."""
        self.clear()
        for label, route in items:
            if route:
                button = GhostButton(label, self)
                button.clicked.connect(lambda _checked=False, key=route: self.route_requested.emit(key))
                self.addWidget(button)
            else:
                self.addWidget(QLabel(label, self))
