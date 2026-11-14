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
from frontend.desktop.themes.tokens import normalize_density, density_metrics

VALID_THEMES = ("light", "dark")
#: Per-terminal appearance store, inside the station data root (SDLC-UI-007).
TERMINAL_SETTINGS_FILENAME = "terminal_appearance.ini"


def _has_touchscreen() -> bool:
    from PyQt5.QtGui import QTouchDevice

    return any(device.type() == QTouchDevice.TouchScreen for device in QTouchDevice.devices())


def _normalize_theme(theme) -> str:
    value = str(getattr(theme, "value", theme)).strip().lower()
    return value if value in VALID_THEMES else "light"


def _current_application():
    """Use the running GUI without creating one during non-GUI startup/tests."""
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance()
    return app if isinstance(app, QApplication) else None


class ThemeManager(QObject):
    theme_changed = pyqtSignal(str)
    density_changed = pyqtSignal(str)
    _instance: "ThemeManager | None" = None

    def __init__(self, settings=None, *, terminal_settings=None, touch_probe=None) -> None:
        super().__init__()
        # Theme is a Windows-user preference; density belongs to the terminal
        # (owner decision SDLC-UI-007, 2026-11-02). An injected ``settings``
        # without a terminal store keeps both in that one store (tests).
        self._settings = settings
        self._terminal_settings = terminal_settings
        self._settings_injected = settings is not None
        self._touch_probe = touch_probe or _has_touchscreen
        self._theme = "light"
        self._density = "comfortable"
        self._listeners: list[Callable[[str], None]] = []

    # singleton ---------------------------------------------------------------
    @classmethod
    def instance(cls) -> "ThemeManager":
        from PyQt5 import sip
        if cls._instance is None or sip.isdeleted(cls._instance):
            cls._instance = cls()
        return cls._instance

    # state -------------------------------------------------------------------
    @property
    def theme(self) -> str:
        return self._theme

    @property
    def density(self) -> str:
        return self._density

    def restore(self, app, *, settings=None, terminal_settings=None) -> None:
        """Restore terminal preferences before constructing login or shell.

        Injected QSettings allow isolated INI files in tests. At runtime the
        theme comes from the Windows user store and the density from the
        station data root (shared by every Windows user of a machine-scope
        installation); no database or authenticated session is needed.
        """
        if settings is not None:
            self._settings = settings
            self._settings_injected = True
        if terminal_settings is not None:
            self._terminal_settings = terminal_settings
        if self._settings is None:
            self._settings = QSettings("JUANIS", "SPJ")
        theme = self._settings.value("appearance/theme", "light")
        self.apply(app, theme, density=self._restored_density())

    def _terminal_store(self):
        if self._terminal_settings is None:
            if self._settings_injected:
                self._terminal_settings = self._settings
            else:
                self._terminal_settings = self._default_terminal_settings() or self._settings
        return self._terminal_settings

    def _restored_density(self) -> str:
        terminal = self._terminal_store()
        density = terminal.value("appearance/density", None) if terminal is not None else None
        if density:
            return density
        # Unconfigured terminal: keep what this Windows user had chosen before
        # density became per terminal, else TOUCH only on a touchscreen.
        if terminal is not self._settings and self._settings is not None:
            density = self._settings.value("appearance/density", None)
        if density:
            return density
        try:
            return "touch" if self._touch_probe() else "comfortable"
        except Exception:
            return "comfortable"

    @staticmethod
    def _default_terminal_settings():
        """INI in the station data root; ``None`` when paths are unavailable."""
        try:
            from backend.shared.app_paths import AppPaths

            folder = AppPaths.from_environment().user_data_dir
            folder.mkdir(parents=True, exist_ok=True)
            return QSettings(str(folder / TERMINAL_SETTINGS_FILENAME), QSettings.IniFormat)
        except Exception:
            return None

    def _persist(self) -> None:
        if self._settings is not None:
            self._settings.setValue("appearance/theme", self._theme)
            terminal = self._terminal_store()
            terminal.setValue("appearance/density", self._density)
            self._settings.sync()
            if terminal is not self._settings:
                terminal.sync()

    def colors(self):
        """Semantic token namespace for the current theme (for chart/HTML use)."""
        return SemanticColors.for_theme(self._theme)

    # application -------------------------------------------------------------
    def apply(self, app, theme: str | None = None, *, density=None) -> None:
        """Apply ``theme`` (or the current one) to a QApplication."""
        previous_theme, previous_density = self._theme, self._density
        if theme is not None:
            self._theme = _normalize_theme(theme)
        if density is not None:
            self._density = normalize_density(density)
        self._persist()
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
            # Painted frames (e.g. the loyalty card preview) draw with Mid.
            (QPalette.Mid, colors.BORDER_STRONG),
        ):
            palette.setColor(role, QColor(color))
        palette.setColor(QPalette.Disabled, QPalette.Text, QColor(colors.TEXT_DISABLED))
        palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(colors.TEXT_DISABLED))
        app.setPalette(palette)
        app.setStyleSheet(build_qss(self._theme, density=self._density))
        # Observers must see one coherent state, including QApplication and QSS.
        if previous_theme != self._theme:
            self._notify_theme_changed()
        if previous_density != self._density:
            self.density_changed.emit(self._density)

    def set_theme(self, theme: str, *, app=None) -> None:
        if app is None:
            app = _current_application()
        if app is not None:
            self.apply(app, theme)
            return
        theme = _normalize_theme(theme)
        changed = theme != self._theme
        self._theme = theme
        self._persist()
        if changed:
            self._notify_theme_changed()

    def _notify_theme_changed(self) -> None:
        self.theme_changed.emit(self._theme)
        for listener in list(self._listeners):
            try:
                listener(self._theme)
            except Exception:
                pass

    def set_density(self, density, *, app=None) -> None:
        if app is None:
            app = _current_application()
        if app is not None:
            self.apply(app, density=density)
            return
        density = normalize_density(density)
        changed = density != self._density
        self._density = density
        self._persist()
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


def bind_input_density(widget):
    """Update specialized inputs without changing their validation inheritance."""
    class Binding(QObject):
        def refresh(self, _density=None):
            widget.setMinimumHeight(density_metrics().input_height)

    binding = Binding(widget)
    widget._spj_density_binding = binding
    binding.refresh()
    ThemeManager.instance().density_changed.connect(binding.refresh)
    return binding
