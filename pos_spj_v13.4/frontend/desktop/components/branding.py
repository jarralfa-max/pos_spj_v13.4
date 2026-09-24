"""Resolve official JUANIS artwork without synthesizing or recoloring logos."""
from __future__ import annotations

from pathlib import Path
import logging
import math
import xml.etree.ElementTree as ET

from PyQt5.QtCore import QByteArray, QRectF, QSize, Qt, QUrl, pyqtSlot
from PyQt5.QtGui import QIcon, QIconEngine, QPainter, QPixmap
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QLabel, QSizePolicy

from backend.shared.app_paths import AppPaths
from frontend.desktop.themes.theme_manager import ThemeManager


def _svg_source(path: Path) -> str | QByteArray:
    """Adapt SVG2 references for Qt5 in memory, leaving original artwork intact."""
    try:
        source = path.read_bytes()
    except OSError:
        return QByteArray()
    try:
        root = ET.fromstring(source)
    except ET.ParseError:
        return str(path)  # QSvgRenderer rejects malformed artwork.
    changed = False
    xlink = "{http://www.w3.org/1999/xlink}href"
    for element in root.iter():
        if "href" in element.attrib and xlink not in element.attrib:
            element.set(xlink, element.attrib["href"])
            changed = True
    if changed:
        # Qt5's SVG reader expects the literal xlink prefix. ElementTree's
        # generated ns1:href is XML-equivalent but not accepted by that reader.
        root.set("xmlns:xlink", "http://www.w3.org/1999/xlink")
        for element in root.iter():
            if xlink in element.attrib:
                reference = element.attrib.pop(xlink)
                url = QUrl(reference)
                if reference and not reference.startswith("#") and url.isRelative():
                    # Loading bytes loses Qt's source directory. Keep local
                    # image references anchored to their original SVG file.
                    reference = (path.parent / url.path()).resolve().as_posix()
                element.set("xlink:href", reference)
        return QByteArray(ET.tostring(root, encoding="utf-8"))
    return str(path)


def _has_visible_artwork(pixmap: QPixmap) -> bool:
    if pixmap.isNull():
        return False
    image = pixmap.toImage()
    return any(image.pixelColor(x, y).alpha() for y in range(image.height()) for x in range(image.width()))


class _BrandSvgIconEngine(QIconEngine):
    """Render the unmodified artwork colors at each requested icon size."""

    def __init__(self, data: str | QByteArray):
        super().__init__()
        self._data = data
        self._renderer = QSvgRenderer(data)

    def clone(self):
        return _BrandSvgIconEngine(self._data)

    def key(self):
        return "spj.brand.svg"

    def actualSize(self, size, mode, state):
        return self._renderer.defaultSize().scaled(size, Qt.KeepAspectRatio)

    def paint(self, painter, rect, mode, state):
        fitted = self.actualSize(rect.size(), mode, state)
        bounds = QRectF(rect.x() + (rect.width() - fitted.width()) / 2,
                        rect.y() + (rect.height() - fitted.height()) / 2,
                        fitted.width(), fitted.height())
        self._renderer.render(painter, bounds)

    def pixmap(self, size, mode, state):
        pixmap = QPixmap(size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        try:
            self.paint(painter, pixmap.rect(), mode, state)
        finally:
            painter.end()
        return pixmap


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
                renderer = QSvgRenderer(_svg_source(path))
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
            if not _has_visible_artwork(artwork):
                logging.getLogger(__name__).warning("Empty brand artwork: %s", path)
                continue
            artwork.setDevicePixelRatio(device_pixel_ratio)
            return artwork
        return QPixmap()

    @classmethod
    def _icon(cls, names, paths):
        for name in names:
            for path in cls._candidates(name, paths):
                icon = QIcon(_BrandSvgIconEngine(_svg_source(path))) if path.suffix == ".svg" else QIcon(str(path))
                if _has_visible_artwork(icon.pixmap(32, 32)):
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
