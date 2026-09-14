"""Real Qt controls, preference restoration and SVG rendering contracts."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QSettings
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QWidget

from frontend.desktop.components.buttons import IconButton, PrimaryButton
from frontend.desktop.components.icons import IconProvider, Icons, all_icons
from frontend.desktop.themes.brand_palette import BrandColors
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import density_metrics


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_official_palette_anchors():
    assert (BrandColors.FOREST_GREEN, BrandColors.WHITE, BrandColors.PREMIUM_GOLD,
            BrandColors.TRADITIONAL_RED, BrandColors.CHARCOAL, BrandColors.WARM_WHITE) == (
        "#18372B", "#FFFFFF", "#C6A15B", "#9D2927", "#252825", "#F8F8F5")


def test_terminal_preferences_restore_before_constructing_controls(app, ui_tmp_path):
    settings = QSettings(str(ui_tmp_path / "appearance.ini"), QSettings.IniFormat)
    manager = ThemeManager(settings)
    manager.set_theme("dark")
    manager.set_density("touch")
    restored = ThemeManager(QSettings(str(ui_tmp_path / "appearance.ini"), QSettings.IniFormat))
    restored.restore(app)
    assert restored.theme == "dark"
    assert restored.density == "touch"
    assert app.property("spjTheme") == "dark"
    assert app.property("spjDensity") == "touch"


def test_stale_qt_singleton_is_recreated(app):
    previous = ThemeManager.instance()
    sip.delete(previous)
    current = ThemeManager.instance()
    assert current is not previous
    current.set_theme("dark", app=app)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("density", ["compact", "comfortable", "touch"])
def test_buttons_follow_density_after_creation(app, theme, density):
    manager = ThemeManager.instance()
    manager.apply(app, theme, density="comfortable")
    host = QWidget()
    row = QHBoxLayout(host)
    button = PrimaryButton("Guardar")
    icon = IconButton(Icons.ADD, "Agregar producto")
    row.addWidget(button)
    row.addWidget(icon)
    manager.set_density(density, app=app)
    host.show()
    app.processEvents()
    metrics = density_metrics(density)
    assert button.height() >= metrics.button_height
    assert icon.width() >= metrics.icon_button_size
    assert icon.height() >= metrics.icon_button_size
    assert not icon.icon().isNull()
    assert not button.styleSheet() and not icon.styleSheet()
    host.close()
    host.deleteLater()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_all_catalog_icons_render_in_every_qicon_mode(app, theme):
    for name in all_icons():
        icon = IconProvider.icon(name, theme=theme)
        for mode in (QIcon.Normal, QIcon.Active, QIcon.Selected, QIcon.Disabled):
            image = icon.pixmap(20, 20, mode).toImage()
            assert not image.isNull(), (name, mode)
            assert any(image.pixelColor(x, y).alpha() for x in range(20) for y in range(20)), name


def test_bound_icon_refreshes_with_theme(app):
    manager = ThemeManager.instance()
    manager.set_theme("light", app=app)
    button = IconButton(Icons.SETTINGS, "Configuración")
    before = button.icon().pixmap(20, 20).toImage()
    manager.set_theme("dark", app=app)
    after = button.icon().pixmap(20, 20).toImage()
    assert before != after


def test_keyboard_action_uses_keyboard_vector_instead_of_fallback_file(app, ui_tmp_path):
    from PyQt5.QtWidgets import QLineEdit
    from frontend.desktop.components.virtual_keyboard import KeyboardAwareInput
    target = QLineEdit()
    controller = KeyboardAwareInput(target, settings=QSettings(str(ui_tmp_path / "keyboard.ini"), QSettings.IniFormat))
    expected = IconProvider.icon(Icons.KEYBOARD).pixmap(20, 20).toImage()
    assert controller.action.icon().pixmap(20, 20).toImage() == expected


def test_responsive_kpis_remain_visible_and_keep_identity_after_resize(app):
    from frontend.desktop.components.kpi_bar import KPIBar
    from frontend.desktop.components.kpi_card import KPIDTO
    bar = KPIBar(cards=[KPIDTO(str(i), f"Indicador {i}", "12") for i in range(4)])
    original = tuple(bar._widgets)
    bar.show()
    for width in (1000, 450, 900, 1000):
        bar.resize(width, 400)
        for _ in range(4):
            app.processEvents()
        assert tuple(bar._widgets) == original
        assert all(card.isVisible() and card.height() >= 96 for card in bar._widgets)
    bar.close()


def test_small_catalog_combobox_displays_selected_label(app):
    from frontend.desktop.components.selection_controls import StandardComboBox
    combo = StandardComboBox(accessible_name="Densidad")
    combo.addItems(["Compacta", "Cómoda", "Táctil"])
    combo.show()
    app.processEvents()
    assert combo.width() > combo.fontMetrics().horizontalAdvance(combo.currentText()) + 20
    combo.close()
