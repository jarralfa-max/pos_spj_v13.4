"""Theme changes must reach live widgets and persist through the real UI."""
from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import QApplication

from frontend.desktop.components import IconButton, StandardLineEdit
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.qss_builder import build_qss
from frontend.desktop.themes.semantic_colors import Dark
from frontend.desktop.themes.theme_manager import ThemeManager


@pytest.fixture
def manager(qt_font_resources, ui_tmp_path, monkeypatch):
    settings = QSettings(str(ui_tmp_path / "theme.ini"), QSettings.IniFormat)
    instance = ThemeManager(settings)
    monkeypatch.setattr(ThemeManager, "_instance", instance)
    instance.apply(qt_font_resources, "light", density="comfortable")
    yield instance


def test_apply_notifies_only_after_theme_and_density_reach_qt(manager, qt_font_resources):
    app = qt_font_resources
    snapshots = []
    def observe(_value):
        snapshots.append((app.property("spjTheme"), app.property("spjDensity"), app.styleSheet()))
    manager.theme_changed.connect(observe)
    manager.density_changed.connect(observe)
    manager.apply(app, "dark", density="touch")
    expected = ("dark", "touch", build_qss("dark", density="touch"))
    assert snapshots == [expected, expected]
    assert app.palette().color(QPalette.Base).name().upper() == Dark.SURFACE


def test_restore_refreshes_existing_icons_and_preserves_input_values(manager, qt_font_resources):
    app = qt_font_resources
    icon = IconButton(Icons.SETTINGS, "Configuración")
    field = StandardLineEdit(keyboard_enabled=False)
    field.setText("Dato en captura")
    before = icon.icon().pixmap(20, 20).toImage()
    manager._settings.setValue("appearance/theme", "dark")
    manager._settings.setValue("appearance/density", "touch")
    observed = []
    manager.theme_changed.connect(observed.append)
    manager.restore(app)
    assert observed == ["dark"]
    assert before != icon.icon().pixmap(20, 20).toImage()
    assert field.text() == "Dato en captura"
    assert field.minimumHeight() >= 52


@pytest.mark.parametrize("stored,expected", [(" DARK ", "dark"), ("LIGHT", "light"), ("sepia", "light")])
def test_restore_keeps_only_two_official_themes(manager, qt_font_resources, stored, expected):
    manager._settings.setValue("appearance/theme", stored)
    manager.restore(qt_font_resources)
    assert manager.theme == expected
    assert manager._settings.value("appearance/theme") == expected


def test_reapplying_the_same_theme_does_not_emit_duplicate_changes(manager, qt_font_resources):
    changes = []
    manager.theme_changed.connect(changes.append)
    manager.apply(qt_font_resources, "light")
    assert changes == []


def test_configuration_changes_live_theme_and_restores_it_on_restart(manager, qt_font_resources):
    from frontend.desktop.modules.configuracion.pages.apariencia_page import AparienciaPage

    presenter = MagicMock()
    presenter.list_density_profiles.return_value = ()
    presenter.list_appearance_preferences.return_value = ()
    page = AparienciaPage(presenter)
    other = AparienciaPage(presenter)
    assert [page.theme_selector.itemText(i) for i in range(page.theme_selector.count())] == ["Claro", "Oscuro"]
    page.theme_selector.setCurrentIndex(page.theme_selector.findData("dark"))
    QApplication.processEvents()
    assert qt_font_resources.property("spjTheme") == "dark"
    assert other.theme_selector.currentData() == "dark"
    assert manager._settings.value("appearance/theme") == "dark"
    restored = ThemeManager(QSettings(manager._settings.fileName(), QSettings.IniFormat))
    restored.restore(qt_font_resources)
    assert restored.theme == "dark"
    presenter.create_theme.assert_not_called()
    presenter.update_theme.assert_not_called()
