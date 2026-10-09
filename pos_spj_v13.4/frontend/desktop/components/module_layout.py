"""Shared module composition, using the Pricing workspace as the reference."""

from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.page_viewport import PageViewport
from frontend.desktop.themes.tokens import Spacing


class ModuleLayout(QVBoxLayout):
    """Keep the module header and navigation outside the content viewport.

    Modules retain ownership of their routes and page stacks. This layout only
    arranges the existing widgets; it neither builds nor replaces their pages.
    A workspace without secondary navigation (POS) can pass ``sidebar=None``.
    """

    def __init__(
        self,
        parent: QWidget,
        *,
        title: str,
        sidebar: QWidget | None,
        content: QWidget,
        subtitle: str = "",
        icon: str | None = None,
    ) -> None:
        super().__init__(parent)
        parent.setProperty("overflowPolicy", "auto")
        self.setContentsMargins(
            Spacing.PAGE_MARGIN_HORIZONTAL, Spacing.PAGE_MARGIN_VERTICAL,
            Spacing.PAGE_MARGIN_HORIZONTAL, Spacing.PAGE_MARGIN_VERTICAL,
        )
        self.setSpacing(Spacing.MD)
        self.header = PageHeader(
            parent, title=title, subtitle=subtitle, icon=icon, compact=True,
        )
        self.addWidget(self.header)

        self.body = QHBoxLayout()
        self.body.setSpacing(Spacing.LG)
        self.addLayout(self.body, stretch=1)
        if sidebar is not None:
            self.body.addWidget(sidebar)
        self.viewport = PageViewport(parent)
        self.viewport.set_page(content)
        self.body.addWidget(self.viewport, stretch=1)

    def add_context(self, widget: QWidget) -> None:
        """Insert module-wide context below the header, before the body."""
        self.insertWidget(self.count() - 1, widget)
