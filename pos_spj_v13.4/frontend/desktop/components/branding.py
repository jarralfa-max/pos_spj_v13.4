"""Resolve official JUANIS artwork without synthesizing or recoloring logos."""
from __future__ import annotations

from pathlib import Path
import logging
import math

from PyQt5.QtCore import QRectF, QSize, Qt, pyqtSlot
from PyQt5.QtGui import QIcon, QPainter, QPixmap
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QLabel, QSizePolicy

from backend.shared.app_paths import AppPaths
from frontend.desktop.themes.theme_manager import ThemeManager


class BrandAssetProvider:
    """Bundled assets live under AppPaths.resource_root/assets/branding.

    Missing artwork remains missing: the UI may show the company name as text,
    but must never present an invented symbol as the official JUANIS logo.
    """

    ASSET_NAMES = (
        "logo_horizontal_light", "logo_horizontal_dark",
        "isotype_light", "isotype_dark", "app_icon", "window_icon",
    )

    @classmethod
    def _candidates(cls, name: str, paths: AppPaths | None = None):
        if name not in cls.ASSET_NAMES:
            raise ValueError(f"Unknown official brand asset: {name}")
        directory = (paths or AppPaths.from_environment()).resource_root / "assets" / "branding"
        for extension in ("svg", "png", "ico"):
            candidate = directory / f"{name}.{extension}"
            if candidate.is_file():
                yield candidate

    @classmethod
    def asset_path(cls, name: str, *, paths: AppPaths | None = None) -> Path | None:
        """First existing candidate; rendering also checks decoding and siblings."""
        return next(cls._candidates(name, paths), None)

    @classmethod
    def pixmap(cls, name: str, size: QSize, *, paths: AppPaths | None = None,
               device_pixel_ratio: float = 1.0) -> QPixmap:
        if not math.isfinite(device_pixel_ratio) or device_pixel_ratio <= 0:
            raise ValueError("Brand device pixel ratio must be finite and positive")
        candidates = tuple(cls._candidates(name, paths))
        if size.isEmpty():
            return QPixmap()
        pixels = QSize(max(1, round(size.width() * device_pixel_ratio)),
                       max(1, round(size.height() * device_pixel_ratio)))
        for path in candidates:
            if path.suffix == ".svg":
                renderer = QSvgRenderer(str(path))
                if not renderer.isValid() or renderer.defaultSize().isEmpty():
                    logging.getLogger(__name__).warning("Unreadable brand artwork: %s", path)
                    continue
                fitted = renderer.defaultSize().scaled(pixels, Qt.KeepAspectRatio)
                artwork = QPixmap(fitted)
                artwork.fill(Qt.transparent)
                painter = QPainter(artwork)
                try:
                    renderer.render(painter, QRectF(artwork.rect()))
                finally:
                    painter.end()
            else:
                artwork = QPixmap(str(path))
                if artwork.isNull():
                    logging.getLogger(__name__).warning("Unreadable brand artwork: %s", path)
                    continue
                artwork = artwork.scaled(pixels, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            artwork.setDevicePixelRatio(device_pixel_ratio)
            return artwork
        return QPixmap()

    @classmethod
    def _icon(cls, names, paths):
        for name in names:
            for path in cls._candidates(name, paths):
                icon = QIcon(str(path))
                if not icon.pixmap(32, 32).isNull():
                    return icon
                logging.getLogger(__name__).warning("Unreadable brand icon: %s", path)
        return QIcon()

    @classmethod
    def window_icon(cls, *, paths: AppPaths | None = None) -> QIcon:
        return cls._icon(("window_icon", "app_icon"), paths)

    @classmethod
    def app_icon(cls, *, paths: AppPaths | None = None) -> QIcon:
        return cls._icon(("app_icon", "window_icon"), paths)

    @classmethod
    def apply_to_application(cls, app, *, paths: AppPaths | None = None) -> None:
        """Set the default application/window icon before constructing the login."""
        app.setWindowIcon(cls.app_icon(paths=paths))


class BrandLabel(QLabel):
    """Theme-aware official logo/isotype with aspect ratio preserved."""

    def __init__(self, parent=None, *, isotype: bool = False,
                 max_size: QSize | None = None, paths: AppPaths | None = None) -> None:
        super().__init__(parent)
        self._isotype = isotype
        self._max_size = max_size or QSize(180, 72)
        self._paths = paths
        self._artwork = QPixmap()
        self._window = None
        self.setObjectName("brandLabel")
        self.setAccessibleName("JUANIS")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
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
        self._artwork = BrandAssetProvider.pixmap(
            name, size, paths=self._paths, device_pixel_ratio=self.devicePixelRatioF())
        self.clear()
        if self._artwork.isNull():
            self.setText("JUANIS")
        else:
            self._fit_artwork()
        self.setToolTip("JUANIS")
        self.updateGeometry()

    def sizeHint(self):
        if self._artwork.isNull():
            return super().sizeHint()
        ratio = self._artwork.devicePixelRatioF()
        return QSize(round(self._artwork.width() / ratio), round(self._artwork.height() / ratio))

    def minimumSizeHint(self):
        return QSize(0, 0) if not self._artwork.isNull() else super().minimumSizeHint()

    def _fit_artwork(self):
        if self._artwork.isNull():
            return
        ratio = self._artwork.devicePixelRatioF()
        available = self.contentsRect().size().boundedTo(self.sizeHint())
        if available.isEmpty():
            self.clear()
            return
        pixels = QSize(max(1, round(available.width() * ratio)),
                       max(1, round(available.height() * ratio)))
        fitted = self._artwork.scaled(pixels, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        fitted.setDevicePixelRatio(ratio)
        self.setPixmap(fitted)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_artwork()

    def showEvent(self, event):
        from PyQt5 import sip
        super().showEvent(event)
        window = self.window().windowHandle()
        if window is not self._window:
            if self._window is not None and not sip.isdeleted(self._window):
                self._window.screenChanged.disconnect(self._screen_changed)
            self._window = window
            if window is not None:
                window.screenChanged.connect(self._screen_changed)
        self._refresh()

    @pyqtSlot()
    def _screen_changed(self):
        self._refresh()
