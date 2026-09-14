"""Synthetic rectangles verify loading; these fixtures are not JUANIS artwork."""
import pytest
from PyQt5.QtCore import QEvent, QSize
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
