"""ImageThumbnail — miniatura de una imagen local con caché (PROD-21).

La usan las tarjetas del POS y la galería de Productos. Sólo presenta: recibe la
referencia que ya resolvió un QueryService (``image_reference``/``uri``) y la
dibuja escalada sin deformar. Si no hay imagen, o el archivo ya no existe,
muestra las iniciales del producto sobre una superficie neutra (rol de tema
``imageThumbnail`` con ``empty=true``) — nunca un hueco en blanco.

La caché evita releer y reescalar el archivo en cada búsqueda del POS (una
cuadrícula de 200 tarjetas se reconstruye con cada tecla). La llave incluye la
fecha de modificación, así que quitar el fondo o restaurar se ve al instante.
"""

from __future__ import annotations

import os
from collections import OrderedDict

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QLabel

_CACHE_LIMIT = 600
_cache: OrderedDict[tuple, QPixmap] = OrderedDict()


def _initials(text: str) -> str:
    words = [w for w in (text or "").split() if w[:1].isalnum()]
    return "".join(w[0] for w in words[:2]).upper() or "?"


def load_thumbnail(reference: str | None, size: QSize, ratio: float = 1.0) -> QPixmap | None:
    """Pixmap escalado a ``size`` (respetando proporción) o ``None`` si no hay archivo."""
    if not reference:
        return None
    try:
        stat = os.stat(reference)
    except OSError:
        return None
    key = (reference, stat.st_mtime_ns, stat.st_size, size.width(), size.height(), ratio)
    cached = _cache.get(key)
    if cached is not None:
        _cache.move_to_end(key)
        return cached
    source = QPixmap(reference)
    if source.isNull():
        return None
    scaled = source.scaled(int(size.width() * ratio), int(size.height() * ratio),
                           Qt.KeepAspectRatio, Qt.SmoothTransformation)
    scaled.setDevicePixelRatio(ratio)
    _cache[key] = scaled
    if len(_cache) > _CACHE_LIMIT:
        _cache.popitem(last=False)
    return scaled


class ImageThumbnail(QLabel):
    def __init__(self, parent=None, *, width: int = 150, height: int = 96) -> None:
        super().__init__(parent)
        self.setObjectName("imageThumbnail")
        self.setProperty("role", "imageThumbnail")
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(width, height)
        self._has_image = False

    def has_image(self) -> bool:
        return self._has_image

    def set_image(self, reference: str | None, *, placeholder: str = "",
                  accessible_name: str = "") -> bool:
        ratio = self.devicePixelRatioF() if self.window() is not None else 1.0
        pixmap = load_thumbnail(reference, self.size(), ratio)
        self._has_image = pixmap is not None
        if pixmap is not None:
            self.setText("")
            self.setPixmap(pixmap)
        else:
            self.setPixmap(QPixmap())
            self.setText(_initials(placeholder))
        self.setAccessibleName(accessible_name or placeholder or "Imagen")
        self.setProperty("empty", "false" if self._has_image else "true")
        self.style().unpolish(self)
        self.style().polish(self)
        return self._has_image
