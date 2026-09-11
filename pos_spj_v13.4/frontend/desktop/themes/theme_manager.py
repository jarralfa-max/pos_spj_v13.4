"""ThemeManager (FASE DS-2) — the single authority that applies a theme.

Only the ThemeManager sets the application stylesheet. Components never accept a
``theme=`` argument as a parallel source of truth; they read the current theme
from here (or simply rely on the QSS applied to the QApplication). The current
theme name is also stamped on the app via a dynamic property so QSS/`property`
selectors and tests can read it.
"""

from __future__ import annotations

from typing import Callable

from PyQt5.QtCore import QObject, QSettings, pyqtSignal
from PyQt5.QtGui import QColor, QPalette

from frontend.desktop.themes.qss_builder import build_qss
from frontend.desktop.themes.semantic_colors import SemanticColors
from frontend.desktop.themes.tokens import normalize_density

VALID_THEMES = ("light", "dark")


class ThemeManager(QObject):
    theme_changed = pyqtSignal(str)
    density_changed = pyqtSignal(str)
    _instance: "ThemeManager | None" = None

    def __init__(self, settings=None) -> None:
        super().__init__()
        self._settings = settings
        self._theme = "light"
        self._density = "comfortable"
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

    @property
    def density(self) -> str:
        return self._density

    def restore(self, app, *, settings=None) -> None:
        """Restore terminal preferences before constructing login or shell.

        An injected QSettings allows isolated INI files in tests. Runtime uses
        the OS user/terminal store; no database or authenticated session is needed.
        """
        if settings is not None:
            self._settings = settings
        if self._settings is None:
            self._settings = QSettings("JUANIS", "SPJ")
        theme = str(self._settings.value("appearance/theme", "light")).lower()
        density = self._settings.value("appearance/density", "comfortable")
        self._theme = theme if theme in VALID_THEMES else "light"
        self._density = normalize_density(density)
        self.apply(app)

    def _persist(self) -> None:
        if self._settings is not None:
            self._settings.setValue("appearance/theme", self._theme)
            self._settings.setValue("appearance/density", self._density)
            self._settings.sync()

    def colors(self):
        """Semantic token namespace for the current theme (for chart/HTML use)."""
        return SemanticColors.for_theme(self._theme)

    # application -------------------------------------------------------------
    def apply(self, app, theme: str | None = None, *, density=None) -> None:
        """Apply ``theme`` (or the current one) to a QApplication."""
        if theme is not None:
            self.set_theme(theme, app=None)  # store without double-applying
        if density is not None:
            self.set_density(density)
        app.setProperty("spjTheme", self._theme)
        app.setProperty("spjDensity", self._density)
        colors = self.colors()
        palette = app.palette()
        for role, color in (
            (QPalette.Window, colors.BACKGROUND), (QPalette.WindowText, colors.TEXT_PRIMARY),
            (QPalette.Base, colors.SURFACE), (QPalette.AlternateBase, colors.SURFACE_MUTED),
            (QPalette.Text, colors.TEXT_PRIMARY), (QPalette.Button, colors.SURFACE),
            (QPalette.ButtonText, colors.TEXT_PRIMARY), (QPalette.Highlight, colors.SELECTION),
            (QPalette.HighlightedText, colors.TEXT_PRIMARY),
            (QPalette.ToolTipBase, colors.TOOLTIP_BACKGROUND),
            (QPalette.ToolTipText, colors.TOOLTIP_TEXT),
            (QPalette.PlaceholderText, colors.TEXT_MUTED),
        ):
            palette.setColor(role, QColor(color))
        palette.setColor(QPalette.Disabled, QPalette.Text, QColor(colors.TEXT_DISABLED))
        palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(colors.TEXT_DISABLED))
        app.setPalette(palette)
        app.setStyleSheet(build_qss(self._theme, density=self._density))

    def set_theme(self, theme: str, *, app=None) -> None:
        theme = str(getattr(theme, "value", theme)).lower()
        theme = theme if theme in VALID_THEMES else "light"
        changed = theme != self._theme
        self._theme = theme
        self._persist()
        if app is not None:
            self.apply(app)
        if changed:
            self.theme_changed.emit(theme)
            for listener in list(self._listeners):
                try:
                    listener(theme)
                except Exception:
                    pass

    def set_density(self, density, *, app=None) -> None:
        density = normalize_density(density)
        changed = density != self._density
        self._density = density
        self._persist()
        if app is not None:
            self.apply(app)
        if changed:
            self.density_changed.emit(density)

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
