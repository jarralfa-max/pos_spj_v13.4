"""ThemeManager (FASE DS-2) — the single authority that applies a theme.

Only the ThemeManager sets the application stylesheet. Components never accept a
``theme=`` argument as a parallel source of truth; they read the current theme
from here (or simply rely on the QSS applied to the QApplication). The current
theme name is also stamped on the app via a dynamic property so QSS/`property`
selectors and tests can read it.
"""

from __future__ import annotations

from typing import Callable

from frontend.desktop.themes.qss_builder import build_qss
from frontend.desktop.themes.semantic_colors import SemanticColors

VALID_THEMES = ("light", "dark")


class ThemeManager:
    _instance: "ThemeManager | None" = None

    def __init__(self) -> None:
        self._theme = "light"
        self._listeners: list[Callable[[str], None]] = []

    # singleton ---------------------------------------------------------------
    @classmethod
    def instance(cls) -> "ThemeManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # state -------------------------------------------------------------------
    @property
    def theme(self) -> str:
        return self._theme

    def colors(self):
        """Semantic token namespace for the current theme (for chart/HTML use)."""
        return SemanticColors.for_theme(self._theme)

    # application -------------------------------------------------------------
    def apply(self, app, theme: str | None = None) -> None:
        """Apply ``theme`` (or the current one) to a QApplication."""
        if theme is not None:
            self.set_theme(theme, app=None)  # store without double-applying
        app.setStyleSheet(build_qss(self._theme))
        try:
            app.setProperty("spjTheme", self._theme)
        except Exception:
            pass

    def set_theme(self, theme: str, *, app=None) -> None:
        theme = theme if theme in VALID_THEMES else "light"
        changed = theme != self._theme
        self._theme = theme
        if app is not None:
            self.apply(app)
        if changed:
            for listener in list(self._listeners):
                try:
                    listener(theme)
                except Exception:
                    pass

    def toggle(self, app=None) -> str:
        self.set_theme("dark" if self._theme == "light" else "light", app=app)
        return self._theme

    # observers ---------------------------------------------------------------
    def subscribe(self, listener: Callable[[str], None]) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unsubscribe(self, listener: Callable[[str], None]) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)
