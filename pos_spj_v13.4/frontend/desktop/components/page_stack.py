"""Page stack whose inactive cached pages cannot enlarge the viewport."""

from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QLayout, QStackedWidget


class PageStack(QStackedWidget):
    """Keep Qt ownership/navigation while sizing only the current page.

    A regular QStackedWidget combines minimum sizes of every cached page.
    This stack lets PageViewport scroll the active page's actual minimum
    without forcing the same overflow on smaller, unrelated pages.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout().setSizeConstraint(QLayout.SetNoConstraint)
        self.currentChanged.connect(self._page_changed)

    def minimumSizeHint(self) -> QSize:
        page = self.currentWidget()
        return page.minimumSizeHint().expandedTo(page.minimumSize()) if page else QSize(0, 0)

    def sizeHint(self) -> QSize:
        page = self.currentWidget()
        return page.sizeHint() if page else QSize(0, 0)

    def heightForWidth(self, width: int) -> int:
        # QScrollArea treats heightForWidth as a minimum. Preferred heights
        # from an inner viewport must not create a redundant outer scrollbar.
        page = self.currentWidget()
        if page is None:
            return 0
        layout = page.layout()
        height = layout.minimumHeightForWidth(width) if layout is not None else page.heightForWidth(width)
        return max(height, self.minimumSizeHint().height())

    def _page_changed(self, _index: int) -> None:
        self.updateGeometry()
