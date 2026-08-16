"""Touch-friendly debounced search input for the SPJ Design System.

SearchInput only emits search intent. It never performs SQL, repository
access or backend queries directly.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer, pyqtSignal

from frontend.desktop.components.icons import Icons
from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.components.tooltip import apply_tooltip


class SearchInput(StandardLineEdit):
    """Standard search field with debounce and virtual keyboard.

    Signals:
        search_changed(str):
            Emitted after the configured debounce interval.

        search_submitted(str):
            Emitted immediately when Enter/Return is pressed.
    """

    search_changed = pyqtSignal(str)
    search_submitted = pyqtSignal(str)

    def __init__(
        self,
        parent=None,
        *,
        placeholder: str = "Buscar…",
        debounce_ms: int = 300,
        keyboard_enabled: bool = True,
        accessible_name: str = "Buscar",
    ) -> None:
        super().__init__(
            parent,
            placeholder=placeholder,
            keyboard_enabled=keyboard_enabled,
            keyboard_numeric=False,
            accessible_name=accessible_name,
        )

        self.setObjectName("searchInput")
        self.setClearButtonEnabled(True)

        # Semantic icon identifier consumed by the Design System/theme.
        self.setProperty("icon", Icons.SEARCH)
        self.setProperty("role", "search")

        apply_tooltip(
            self,
            "Buscar",
            shortcut="Ctrl+F",
        )

        # --------------------------------------------------------------
        # Debounce
        # --------------------------------------------------------------

        self._debounce_ms = max(0, int(debounce_ms))

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self._debounce_ms)

        self._timer.timeout.connect(self._emit_search_changed)

        self.textChanged.connect(self._schedule_search)
        self.returnPressed.connect(self._submit_search)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def query(self) -> str:
        """Return normalized search text."""
        return self.value()

    def debounce_ms(self) -> int:
        return self._debounce_ms

    def set_debounce_ms(self, debounce_ms: int) -> None:
        """Change debounce interval at runtime."""
        self._debounce_ms = max(0, int(debounce_ms))
        self._timer.setInterval(self._debounce_ms)

    def clear_search(self) -> None:
        """Clear the query and immediately notify listeners."""
        self._timer.stop()

        if not self.text():
            self.search_changed.emit("")
            return

        # clear() emits textChanged synchronously, which starts the timer.
        self.clear()

        # Prevent a second duplicate emission after debounce.
        self._timer.stop()
        self.search_changed.emit("")

    def submit(self) -> None:
        """Programmatically submit the current search."""
        self._submit_search()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _schedule_search(self, _text: str) -> None:
        if self._debounce_ms == 0:
            self._timer.stop()
            self._emit_search_changed()
            return

        self._timer.start()

    def _emit_search_changed(self) -> None:
        self.search_changed.emit(self.query())

    def _submit_search(self) -> None:
        # A submitted search must not later produce an old delayed debounce.
        self._timer.stop()

        query = self.query()
        self.search_submitted.emit(query)

    # ------------------------------------------------------------------
    # Qt events
    # ------------------------------------------------------------------

    def keyPressEvent(self, event):  # noqa: N802 - Qt override
        if event.key() == Qt.Key_Escape:
            if self.text():
                self.clear_search()
                return

        super().keyPressEvent(event)