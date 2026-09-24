"""Exercise supplied JUANIS artwork with the application's actual Qt decoder.

These checks protect asset availability and rendering, not artistic approval.
Additional supplied files are allowed; only the six canonical roles are required.
"""
from pathlib import Path

import pytest
from PyQt5.QtCore import QSize
from PyQt5.QtGui import QImage
from PyQt5.QtSvg import QSvgRenderer

from backend.shared.app_paths import AppPaths
from frontend.desktop.components.branding import BrandAssetProvider


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_PATHS = AppPaths(base_dir=PACKAGE_ROOT)
REQUIRED_ASSETS = (
    "logo_horizontal_light", "logo_horizontal_dark",
    "isotype_light", "isotype_dark", "app_icon", "window_icon",
)


def _has_visible_pixels(pixmap):
    """A valid Qt image may still be completely transparent after SVG parsing."""
    image = pixmap.toImage().convertToFormat(QImage.Format_RGBA8888)
    if image.isNull():
        return False
    pointer = image.constBits()
    pointer.setsize(image.byteCount())
    return any(bytes(pointer)[3::4])


@pytest.mark.parametrize("name", REQUIRED_ASSETS)
@pytest.mark.parametrize("ratio", [1.0, 2.0])
def test_required_official_artwork_is_visible_and_keeps_proportions(qt_font_resources, name, ratio):
    path = BrandAssetProvider.asset_path(name, paths=OFFICIAL_PATHS)
    assert path is not None, f"Missing supplied official artwork: {name}"
    if path.suffix == ".svg":
        renderer = QSvgRenderer(str(path))
        assert renderer.isValid(), f"Qt cannot decode {path.name}"
        original_size = renderer.defaultSize()
    else:
        original = QImage(str(path))
        assert not original.isNull(), f"Qt cannot decode {path.name}"
        original_size = original.size()
    assert not original_size.isEmpty()

    bounds = QSize(180, 72) if name.startswith("logo_horizontal") else QSize(40, 40)
    pixmap = BrandAssetProvider.pixmap(name, bounds, paths=OFFICIAL_PATHS, device_pixel_ratio=ratio)
    assert not pixmap.isNull(), f"Qt cannot render {path.name}"
    assert _has_visible_pixels(pixmap), f"{path.name} decodes but renders completely transparent"
    assert pixmap.devicePixelRatioF() == ratio
    assert pixmap.width() <= bounds.width() * ratio
    assert pixmap.height() <= bounds.height() * ratio
    # Integer raster dimensions can round by one physical pixel.
    expected_width = pixmap.height() * original_size.width() / original_size.height()
    assert abs(pixmap.width() - expected_width) <= max(1.0, original_size.width() / original_size.height())


@pytest.mark.parametrize("method_name", ["app_icon", "window_icon"])
def test_supplied_official_icons_have_visible_pixels(qt_font_resources, method_name):
    icon = getattr(BrandAssetProvider, method_name)(paths=OFFICIAL_PATHS)
    assert not icon.isNull()
    pixmap = icon.pixmap(32, 32)
    assert _has_visible_pixels(pixmap), f"Official {method_name} is invisible in a window title bar"
