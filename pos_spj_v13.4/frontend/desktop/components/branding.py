"""Resolve official JUANIS artwork without synthesizing or recoloring logos."""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QLabel

from backend.shared.app_paths import AppPaths
from frontend.desktop.themes.theme_manager import ThemeManager


class BrandAssetProvider:
    """Bundled assets live under AppPaths.root/assets/branding.

    Missing artwork remains missing: the UI may show the company name as text,
    but must never present an invented symbol as the official JUANIS logo.
    """

    ASSET_NAMES = (
        "logo_horizontal_light", "logo_horizontal_dark",
        "isotype_light", "isotype_dark", "app_icon", "window_icon",
    )

    @classmethod
    def asset_path(cls, name: str, *, paths: AppPaths | None = None) -> Path | None:
        if name not in cls.ASSET_NAMES:
            raise ValueError(f"Unknown official brand asset: {name}")
        directory = (paths or AppPaths.from_environment()).root / "assets" / "branding"
        for extension in ("svg", "png", "ico"):
            candidate = directory / f"{name}.{extension}"
            if candidate.is_file():
                return candidate
        return None

    @classmethod
    def pixmap(cls, name: str, size: QSize, *, paths: AppPaths | None = None) -> QPixmap:
        path = cls.asset_path(name, paths=paths)
        if path is None:
            return QPixmap()
        return QPixmap(str(path)).scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    @classmethod
    def window_icon(cls) -> QIcon:
        path = cls.asset_path("window_icon") or cls.asset_path("app_icon")
        return QIcon(str(path)) if path else QIcon()

    @classmethod
    def app_icon(cls) -> QIcon:
        path = cls.asset_path("app_icon") or cls.asset_path("window_icon")
        return QIcon(str(path)) if path else QIcon()


class BrandLabel(QLabel):
    """Theme-aware official logo/isotype with aspect ratio preserved."""

    def __init__(self, parent=None, *, isotype: bool = False,
                 max_size: QSize | None = None) -> None:
        super().__init__(parent)
        self._isotype = isotype
        self._max_size = max_size or QSize(180, 72)
        self.setObjectName("brandLabel")
        self.setAccessibleName("JUANIS")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(0)
        ThemeManager.instance().theme_changed.connect(self._refresh)
        self._refresh()

    def set_isotype(self, isotype: bool) -> None:
        self._isotype = bool(isotype)
        self._refresh()

    def _refresh(self, *_args) -> None:
        theme = ThemeManager.instance().theme
        suffix = "dark" if "dark" in theme else "light"
        name = f"{'isotype' if self._isotype else 'logo_horizontal'}_{suffix}"
        size = QSize(40, 40) if self._isotype else self._max_size
        artwork = BrandAssetProvider.pixmap(name, size)
        self.clear()
        if artwork.isNull():
            self.setText("JUANIS")
            self.setToolTip("JUANIS — recurso de marca oficial pendiente de incorporar")
        else:
            self.setPixmap(artwork)
            self.setToolTip("JUANIS")
