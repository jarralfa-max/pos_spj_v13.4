"""Canonical overflow boundary between a page and its available workspace."""

from weakref import WeakKeyDictionary

from PyQt5.QtCore import QPoint, QSize, Qt, QTimer
from PyQt5.QtWidgets import QFrame, QScrollArea, QSizePolicy, QStackedWidget, QWidget


class PageViewport(QScrollArea):
    """Expand content and scroll its actual minimum in either direction.

    Headers/navigation/actions belong beside this widget, outside its body.
    A PageStack supplies active-page sizing; its cached pages retain independent
    scroll positions for the lifetime of their widgets, without persisting data.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("pageViewport")
        self.setProperty("overflowPolicy", "auto")
        self.setFrameShape(QFrame.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAccessibleName("Contenido desplazable")
        self._stack: QStackedWidget | None = None
        self._active_page: QWidget | None = None
        self._positions = WeakKeyDictionary()
        self._pending_position: QPoint | None = None
        self._restore_timer = QTimer(self)
        self._restore_timer.setSingleShot(True)
        self._restore_timer.timeout.connect(self._restore_position)
        self.horizontalScrollBar().valueChanged.connect(self._remember_position)
        self.verticalScrollBar().valueChanged.connect(self._remember_position)

    def minimumSizeHint(self) -> QSize:
        # A large form must enlarge its scrollable content, never the shell.
        return QSize(0, 0)

    def set_page(self, page: QWidget) -> None:
        self.setWidget(page)

    def setWidget(self, widget: QWidget) -> None:
        if widget is self.widget():
            return
        self._detach_stack()
        super().setWidget(widget)
        if isinstance(widget, QStackedWidget):
            self._stack = widget
            widget.currentChanged.connect(self._page_changed)
            self._page_changed(widget.currentIndex())

    def takeWidget(self) -> QWidget | None:
        self._detach_stack()
        return super().takeWidget()

    def _detach_stack(self) -> None:
        self._restore_timer.stop()
        if self._stack is not None:
            self._stack.currentChanged.disconnect(self._page_changed)
        self._stack = None
        self._active_page = None
        self._pending_position = None
        self._positions.clear()

    def _remember_position(self, _value: int = 0) -> None:
        # During a switch Qt can clamp the old scroll range or reveal the new
        # focus widget before emitting currentChanged. Neither may overwrite
        # the outgoing page's position.
        if (self._pending_position is not None or self._stack is None
                or self._active_page is None
                or self._stack.currentWidget() is not self._active_page):
            return
        self._positions[self._active_page] = QPoint(
            self.horizontalScrollBar().value(), self.verticalScrollBar().value()
        )

    def _page_changed(self, _index: int) -> None:
        self._active_page = self._stack.currentWidget()
        self._pending_position = self._positions.get(self._active_page, QPoint()) if self._active_page else QPoint()
        # Let Qt apply the new page's layout and scroll ranges first. Restarting
        # one owned timer also coalesces lazy page replacement and rapid routing.
        self._restore_timer.start(0)

    def _restore_position(self) -> None:
        position = self._pending_position
        if position is None:
            return
        self.horizontalScrollBar().setValue(position.x())
        self.verticalScrollBar().setValue(position.y())
        self._pending_position = None
        self._remember_position()

    def page(self) -> QWidget | None:
        return self.widget()

    def viewport_size(self) -> QSize:
        return self.viewport().size()
