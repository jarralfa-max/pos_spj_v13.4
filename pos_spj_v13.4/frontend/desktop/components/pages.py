"""Page structures sharing one overflow policy and sticky page actions."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QSplitter, QStackedWidget, QVBoxLayout, QWidget

from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.dashboard_grid import DashboardGrid
from frontend.desktop.components.kpi_bar import KPIBar
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.page_viewport import PageViewport
from frontend.desktop.components.tabs import Tabs
from frontend.desktop.components.toolbar import ContextBar
from frontend.desktop.themes.tokens import Spacing


class StandardPage(QWidget):
    """Sticky header, expanding scrollable content, optional sticky actions."""

    def __init__(self, parent=None, *, title="", subtitle="") -> None:
        super().__init__(parent)
        self.setObjectName("standardPage")
        self.setProperty("overflowPolicy", "auto")
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        self.root_layout.setSpacing(Spacing.MD)
        self.header = PageHeader(title=title, subtitle=subtitle)
        self.root_layout.addWidget(self.header)
        self.viewport = PageViewport(self)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(Spacing.MD)
        self.viewport.set_page(self.content)
        self.root_layout.addWidget(self.viewport, 1)
        self.actions = QWidget(self)
        self.actions.setObjectName("stickyActions")
        self.actions_layout = QHBoxLayout(self.actions)
        self.actions_layout.setContentsMargins(0, 0, 0, 0)
        self.actions_layout.addStretch()
        self.root_layout.addWidget(self.actions)
        self.actions.hide()

    def add_content(self, widget: QWidget, stretch: int = 0) -> None:
        self.content_layout.addWidget(widget, stretch)

    def add_action(self, widget: QWidget) -> None:
        self.actions_layout.addWidget(widget)
        self.actions.show()


class ScrollablePage(StandardPage):
    """Explicit name for pages whose body is a scrolling document."""


class FormPage(StandardPage):
    """The form body scrolls while save/cancel actions remain reachable."""


class DashboardPage(StandardPage):
    def __init__(self, parent=None, **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self.context_bar = ContextBar(self)
        self.add_content(self.context_bar)
        self.kpis = KPIBar(self)
        self.add_content(self.kpis)
        self.grid = DashboardGrid(self)
        self.add_content(self.grid, 1)


class SplitPage(StandardPage):
    def __init__(self, parent=None, *, master=None, detail=None, **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self.splitter = QSplitter(Qt.Horizontal, self.content)
        self.splitter.setChildrenCollapsible(False)
        for widget in (master, detail):
            if widget is not None:
                self.splitter.addWidget(widget)
        self.add_content(self.splitter, 1)


class MasterDetailPage(SplitPage):
    """Two related panes in one resizable, scroll-safe workspace."""


class TabbedPage(StandardPage):
    def __init__(self, parent=None, **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self.tabs = Tabs(self.content)
        self.add_content(self.tabs, 1)


class POSPage(SplitPage):
    """Sales workspace; touch sizing is inherited by canonical controls."""

    def __init__(self, parent=None, **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self.setProperty("density", "touch")


class WizardPage(StandardPage):
    """Sequential content with keyboard-reachable previous/next actions."""

    def __init__(self, parent=None, **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self.steps = QStackedWidget(self.content)
        self.add_content(self.steps, 1)
        self.previous_button = create_secondary_button(self, "Anterior")
        self.next_button = create_primary_button(self, "Siguiente")
        self.add_action(self.previous_button)
        self.add_action(self.next_button)
        self.previous_button.clicked.connect(lambda: self.steps.setCurrentIndex(self.steps.currentIndex() - 1))
        self.next_button.clicked.connect(lambda: self.steps.setCurrentIndex(self.steps.currentIndex() + 1))
        self.steps.currentChanged.connect(self._step_changed)
        self._step_changed(-1)

    def add_step(self, widget: QWidget) -> int:
        index = self.steps.addWidget(widget)
        self._step_changed(self.steps.currentIndex())
        return index

    def _step_changed(self, index: int) -> None:
        self.previous_button.setEnabled(index > 0)
        self.next_button.setEnabled(0 <= index < self.steps.count() - 1)
