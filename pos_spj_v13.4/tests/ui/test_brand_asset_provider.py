"""Synthetic rectangles verify loading; these fixtures are not JUANIS artwork."""
import pytest
from PyQt5.QtCore import QEvent, QSize, Qt
from PyQt5.QtGui import QColor, QImage

from backend.shared.app_paths import AppPaths
from frontend.desktop.components.branding import BrandAssetProvider, BrandLabel
from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.components.standard_window import StandardWindow
from frontend.desktop.themes.theme_manager import ThemeManager


@pytest.fixture
def assets(qt_font_resources, ui_tmp_path, monkeypatch):
    paths = AppPaths(base_dir=ui_tmp_path)
    directory = paths.root / "assets" / "branding"
    directory.mkdir(parents=True)
    monkeypatch.setattr(AppPaths, "from_environment", classmethod(lambda cls: paths))
    manager = ThemeManager()
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(qt_font_resources, "light")
    return directory


def svg(directory, name, *, color="#4060A0", width=400, height=100):
    path = directory / f"{name}.svg"
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
                    f'viewBox="0 0 {width} {height}"><rect width="{width}" height="{height}" '
                    f'fill="{color}"/></svg>', encoding="utf-8")
    return path


def png(directory, name, *, color="#4060A0"):
    image = QImage(400, 100, QImage.Format_ARGB32)
    image.fill(QColor(color))
    path = directory / f"{name}.png"
    assert image.save(str(path))
    return path


@pytest.mark.parametrize("writer", [svg, png])
def test_artwork_keeps_colors_and_aspect_ratio(assets, writer):
    writer(assets, "logo_horizontal_light")
    result = BrandAssetProvider.pixmap("logo_horizontal_light", QSize(180, 72))
    assert result.size() == QSize(180, 45)
    assert result.toImage().pixelColor(90, 22).name() == "#4060a0"


@pytest.mark.parametrize("extension", ["svg", "png", "ico"])
def test_transparent_artwork_is_preserved_in_all_supported_formats(assets, extension):
    """Fixture geometry tests alpha; it is not an approved logo or isotype."""
    path = assets / f"isotype_light.{extension}"
    if extension == "svg":
        path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">'
            '<rect x="16" y="16" width="32" height="32" fill="#4060A0"/></svg>',
            encoding="utf-8",
        )
    else:
        from PyQt5.QtGui import QPainter

        image = QImage(64, 64, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.fillRect(16, 16, 32, 32, QColor("#4060A0"))
        painter.end()
        assert image.save(str(path))
    result = BrandAssetProvider.pixmap("isotype_light", QSize(32, 32), device_pixel_ratio=2.0)
    assert result.size() == QSize(64, 64)
    assert result.devicePixelRatioF() == 2.0
    assert result.toImage().pixelColor(0, 0).alpha() == 0
    assert result.toImage().pixelColor(32, 32) == QColor("#4060A0")


@pytest.mark.parametrize("ratio", [0, -1, float("nan"), float("inf")])
def test_invalid_device_pixel_ratio_fails_explicitly(assets, ratio):
    with pytest.raises(ValueError, match="pixel ratio"):
        BrandAssetProvider.pixmap("logo_horizontal_light", QSize(180, 72), device_pixel_ratio=ratio)


@pytest.mark.parametrize("consumer", ["pixmap", "window", "application"])
def test_svg2_embedded_image_is_visible_without_rewriting_original(assets, consumer):
    import base64

    source = png(assets, "isotype_light")
    name = "app_icon" if consumer == "application" else "window_icon"
    data = base64.b64encode(source.read_bytes()).decode("ascii")
    original = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="100" viewBox="0 0 400 100">'
        f'<image width="400" height="100" href="data:image/png;base64,{data}"/></svg>'
    ).encode("utf-8")
    path = assets / f"{name}.svg"
    path.write_bytes(original)
    for size in (32, 256):
        if consumer == "pixmap":
            image = BrandAssetProvider.pixmap(name, QSize(size, size)).toImage()
        else:
            icon = BrandAssetProvider.app_icon() if consumer == "application" else BrandAssetProvider.window_icon()
            image = icon.pixmap(size, size).toImage()
        assert not image.isNull()
        assert image.pixelColor(image.width() // 2, image.height() // 2) == QColor("#4060A0")
    assert path.read_bytes() == original


@pytest.mark.parametrize("reference", ["href", "xlink:href"])
@pytest.mark.parametrize("consumer", ["pixmap", "icon"])
def test_svg_local_images_resolve_relative_to_the_artwork_directory(assets, reference, consumer):
    png(assets, "isotype_light")
    path = assets / "window_icon.svg"
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        'width="400" height="100">'
        f'<image width="400" height="100" {reference}="isotype_light.png"/></svg>',
        encoding="utf-8",
    )
    result = (BrandAssetProvider.pixmap("window_icon", QSize(80, 20)) if consumer == "pixmap"
              else BrandAssetProvider.window_icon().pixmap(80, 20))
    assert not result.isNull()
    assert result.toImage().pixelColor(40, 10) == QColor("#4060A0")


@pytest.mark.parametrize("consumer", ["pixmap", "icon"])
def test_transparent_svg_does_not_hide_a_visible_sibling(assets, consumer):
    (assets / "window_icon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="100"/>', encoding="utf-8")
    png(assets, "window_icon")
    result = (BrandAssetProvider.pixmap("window_icon", QSize(80, 20)) if consumer == "pixmap"
              else BrandAssetProvider.window_icon().pixmap(80, 20))
    assert not result.isNull()
    assert result.toImage().pixelColor(40, 10) == QColor("#4060A0")


@pytest.mark.parametrize("ratio", [1.25, 1.5, 2.0, 3.0])
def test_svg_renders_at_physical_resolution_with_logical_size(assets, ratio):
    svg(assets, "logo_horizontal_light")
    result = BrandAssetProvider.pixmap("logo_horizontal_light", QSize(160, 40), device_pixel_ratio=ratio)
    assert result.size() == QSize(round(160 * ratio), round(40 * ratio))
    assert result.devicePixelRatioF() == ratio


def test_corrupt_preferred_format_does_not_hide_valid_sibling(assets):
    (assets / "logo_horizontal_light.svg").write_text("invalid", encoding="utf-8")
    png(assets, "logo_horizontal_light")
    assert not BrandAssetProvider.pixmap("logo_horizontal_light", QSize(180, 72)).isNull()


def test_window_icon_uses_decodable_app_icon_if_window_asset_is_corrupt(assets):
    (assets / "window_icon.svg").write_text("invalid", encoding="utf-8")
    png(assets, "app_icon")
    assert not BrandAssetProvider.window_icon().pixmap(32, 32).isNull()


def test_missing_theme_variant_does_not_recolor_opposite_logo(assets, qt_font_resources):
    svg(assets, "logo_horizontal_light")
    label = BrandLabel()
    try:
        assert label.pixmap() and not label.pixmap().isNull()
        ThemeManager.instance().set_theme("dark", app=qt_font_resources)
        assert label.text() == "JUANIS"
        assert label.pixmap() is None or label.pixmap().isNull()
    finally:
        label.deleteLater()


def test_label_fits_available_width_and_preserves_theme_isotype(assets, qt_font_resources):
    svg(assets, "logo_horizontal_light")
    svg(assets, "logo_horizontal_dark", color="#A06040")
    svg(assets, "isotype_dark", color="#60A040", width=100, height=100)
    label = BrandLabel()
    try:
        label.resize(60, 72)
        label.show()
        qt_font_resources.processEvents()
        assert label.pixmap().width() <= label.contentsRect().width()
        assert label.pixmap().width() == label.pixmap().height() * 4
        ThemeManager.instance().set_theme("dark", app=qt_font_resources)
        assert label.pixmap().toImage().pixelColor(10, 5).name() == "#a06040"
        label.set_isotype(True)
        assert label.pixmap().size() == QSize(40, 40)
        assert label.pixmap().toImage().pixelColor(20, 20).name() == "#60a040"
    finally:
        label.close()
        label.deleteLater()
        qt_font_resources.sendPostedEvents(None, QEvent.DeferredDelete)


def test_label_rerenders_for_the_new_screen_dpi(assets, qt_font_resources, monkeypatch):
    svg(assets, "logo_horizontal_light")
    label = BrandLabel()
    try:
        label.resize(180, 72)
        label.show()
        qt_font_resources.processEvents()
        monkeypatch.setattr(label, "devicePixelRatioF", lambda: 2.0)
        label.windowHandle().screenChanged.emit(label.windowHandle().screen())
        assert label.pixmap().devicePixelRatioF() == 2.0
        assert label.pixmap().size() == QSize(360, 90)
    finally:
        label.close()
        label.deleteLater()
        qt_font_resources.sendPostedEvents(None, QEvent.DeferredDelete)


def test_label_restores_full_artwork_after_shrinking(assets, qt_font_resources, monkeypatch):
    from PyQt5 import sip

    svg(assets, "logo_horizontal_light")
    label = BrandLabel()
    monkeypatch.setattr(label, "devicePixelRatioF", lambda: 1.0)
    try:
        label.resize(180, 72)
        label.show()
        qt_font_resources.processEvents()
        original = label.pixmap().toImage()
        assert original.size() == QSize(180, 45)

        for width in (60, 20, 180):
            label.resize(width, 72)
            qt_font_resources.processEvents()
            image = label.pixmap().toImage()
            assert image.size() == QSize(width, width // 4)
            assert image.pixelColor(image.width() // 2, image.height() // 2) == QColor("#4060A0")

        assert label.pixmap().toImage() == original
    finally:
        sip.delete(label)


def test_reparented_label_follows_only_its_current_window_dpi(assets, qt_font_resources, monkeypatch):
    from PyQt5 import sip
    from PyQt5.QtWidgets import QWidget

    svg(assets, "logo_horizontal_light")
    first, second = QWidget(), QWidget()
    label = BrandLabel(first)
    screen_ratio = [1.0]
    monkeypatch.setattr(label, "devicePixelRatioF", lambda: screen_ratio[0])
    try:
        for window in (first, second):
            window.resize(300, 120)
            window.show()
        label.resize(180, 72)
        label.show()
        qt_font_resources.processEvents()
        first_handle, second_handle = first.windowHandle(), second.windowHandle()
        assert first_handle is not second_handle
        assert label.pixmap().devicePixelRatioF() == 1.0

        screen_ratio[0] = 2.0
        label.setParent(second)
        label.show()
        qt_font_resources.processEvents()
        assert label.pixmap().devicePixelRatioF() == 2.0
        assert label.pixmap().size() == QSize(360, 90)

        screen_ratio[0] = 3.0
        first_handle.screenChanged.emit(first_handle.screen())
        assert label.pixmap().devicePixelRatioF() == 2.0
        assert label.pixmap().size() == QSize(360, 90)

        second_handle.screenChanged.emit(second_handle.screen())
        assert label.pixmap().devicePixelRatioF() == 3.0
        assert label.pixmap().size() == QSize(540, 135)
        assert label.pixmap().toImage().pixelColor(270, 67) == QColor("#4060A0")
    finally:
        sip.delete(label)
        sip.delete(first)
        sip.delete(second)


def test_standard_windows_and_dialogs_use_official_window_icon(assets):
    png(assets, "window_icon")
    window, dialog = StandardWindow(), StandardDialog()
    try:
        for host in (window, dialog):
            assert not host.windowIcon().pixmap(32, 32).isNull()
    finally:
        window.deleteLater()
        dialog.deleteLater()


def test_missing_assets_remain_absent_and_unknown_names_fail(assets):
    for name in BrandAssetProvider.ASSET_NAMES:
        assert BrandAssetProvider.asset_path(name) is None
        assert BrandAssetProvider.pixmap(name, QSize(40, 40)).isNull()
    assert BrandAssetProvider.app_icon().isNull()
    assert BrandAssetProvider.window_icon().isNull()
    with pytest.raises(ValueError):
        BrandAssetProvider.asset_path("../logo")


def test_application_icon_uses_the_official_app_asset(assets, qt_font_resources):
    png(assets, "app_icon")
    previous = qt_font_resources.windowIcon()
    try:
        BrandAssetProvider.apply_to_application(qt_font_resources)
        image = qt_font_resources.windowIcon().pixmap(32, 32).toImage()
        assert not image.isNull()
        assert image.pixelColor(image.width() // 2, image.height() // 2).name() == "#4060a0"
    finally:
        qt_font_resources.setWindowIcon(previous)


def test_provider_uses_separate_resource_root(assets, ui_tmp_path):
    svg(assets, "logo_horizontal_light")
    paths = AppPaths(base_dir=ui_tmp_path / "installation", resource_dir=ui_tmp_path)
    assert BrandAssetProvider.asset_path("logo_horizontal_light", paths=paths) == assets / "logo_horizontal_light.svg"
    assert not BrandAssetProvider.pixmap("logo_horizontal_light", QSize(180, 72), paths=paths).isNull()


def test_login_and_sidebar_share_theme_variants_and_collapse_policy(assets, qt_font_resources):
    from types import SimpleNamespace
    from frontend.desktop.auth.login_window import LoginWindow
    from frontend.desktop.shell.sidebar.global_sidebar import GlobalSidebar

    svg(assets, "logo_horizontal_light")
    svg(assets, "logo_horizontal_dark", color="#A06040")
    svg(assets, "isotype_dark", color="#60A040", width=100, height=100)
    summary = SimpleNamespace(get_summary=lambda: SimpleNamespace(company_name="Prueba", branch_name="Prueba"))
    login = LoginWindow(authenticate_use_case=None, begin_recovery_use_case=None,
                        complete_recovery_use_case=None, installation_summary_query=summary)
    sidebar = GlobalSidebar()
    try:
        login.show()
        sidebar.show()
        qt_font_resources.processEvents()
        ThemeManager.instance().set_theme("dark", app=qt_font_resources)
        label = login.findChild(BrandLabel)
        assert label is not None
        for brand in (label, sidebar._brand):
            image = brand.pixmap().toImage()
            assert image.pixelColor(image.width() // 2, image.height() // 2).name() == "#a06040"
        sidebar.set_collapsed(True)
        qt_font_resources.processEvents()
        assert sidebar._brand.pixmap().size() == QSize(40, 40)
        assert sidebar._brand.pixmap().toImage().pixelColor(20, 20).name() == "#60a040"
        assert label.pixmap().width() == label.pixmap().height() * 4
    finally:
        login.close()
        sidebar.close()
        login.deleteLater()
        sidebar.deleteLater()
        qt_font_resources.sendPostedEvents(None, QEvent.DeferredDelete)
