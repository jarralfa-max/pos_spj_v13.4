"""Terminal density selection must update the live UI without changing admin data."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtTest import QSignalSpy, QTest
from PyQt5.QtWidgets import QLabel

from frontend.desktop.modules.configuracion.pages.apariencia_page import AparienciaPage
from frontend.desktop.themes.qss_builder import build_qss
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import density_metrics


PROFILES = (("Compacta", "compact"), ("Cómoda", "comfortable"), ("Táctil", "touch"))


@pytest.fixture
def terminal(qt_font_resources, ui_tmp_path, monkeypatch):
    settings = QSettings(str(ui_tmp_path / "terminal.ini"), QSettings.IniFormat)
    manager = ThemeManager(settings)
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(qt_font_resources, "light", density="comfortable")
    pages = []

    def create_page():
        presenter = MagicMock()
        presenter.load_page.return_value = SimpleNamespace(
            columns=(SimpleNamespace(title="Tema", kind="text"),),
            rows=(SimpleNamespace(entity_id="0195a854-19c4-7000-8000-000000000001", cells=("Tema activo",)),),
            empty_message="No hay temas registrados.",
        )
        presenter.list_themes.return_value = ()
        presenter.list_density_profiles.return_value = ()
        presenter.list_appearance_preferences.return_value = ()
        presenter.list_design_tokens_for_theme.return_value = ()
        page = AparienciaPage(presenter)
        pages.append(page)
        return page, presenter

    yield qt_font_resources, manager, settings, create_page
    for page in pages:
        if not sip.isdeleted(page):
            sip.delete(page)


@pytest.mark.parametrize("density", [value for _, value in PROFILES])
def test_selector_uses_restored_terminal_profile_and_explains_touch_use(terminal, density):
    app, manager, settings, create_page = terminal
    settings.setValue("appearance/density", density)
    manager.restore(app)
    changes = QSignalSpy(manager.density_changed)
    page, presenter = create_page()

    selector = page.density_selector
    assert [(selector.itemText(i), selector.itemData(i)) for i in range(selector.count())] == list(PROFILES)
    assert selector.currentData() == density
    assert selector.accessibleName() == "Densidad de esta terminal"
    assert len(changes) == 0
    hints = " ".join(label.text() for label in page.findChildren(QLabel))
    for term in ("Táctil", "POS", "Inventario", "Recepción", "Producción"):
        assert term in hints
    presenter.create_density_profile.assert_not_called()
    presenter.update_density_profile.assert_not_called()


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("density", [value for _, value in PROFILES])
def test_keyboard_selection_applies_persists_and_preserves_live_page(terminal, theme, density):
    app, manager, settings, create_page = terminal
    manager.apply(app, theme, density="touch" if density == "comfortable" else "comfortable")
    page, presenter = create_page()
    page.ensure_loaded()
    page.table.selectRow(0)
    page.search.blockSignals(True)
    page.search.setText("Referencia en captura")
    page.search.blockSignals(False)
    selected_row = page.table.selected_row_id()
    calls_before = list(presenter.mock_calls)
    changes = QSignalSpy(manager.density_changed)
    selector = page.density_selector
    target = selector.findData(density)
    key = Qt.Key_Down if target > selector.currentIndex() else Qt.Key_Up
    for _ in range(abs(target - selector.currentIndex())):
        QTest.keyClick(selector, key)
    app.processEvents()

    assert manager.density == density
    assert app.property("spjDensity") == density
    assert app.styleSheet() == build_qss(theme, density=density)
    assert manager.theme == theme
    assert page.theme_selector.currentData() == theme
    assert selector.minimumHeight() == density_metrics(density).input_height
    assert page.search.text() == "Referencia en captura"
    assert page.table.selected_row_id() == selected_row
    assert presenter.mock_calls == calls_before
    assert changes[-1] == [density]
    assert settings.value("appearance/density") == density
    restored = ThemeManager(QSettings(settings.fileName(), QSettings.IniFormat))
    restored.restore(app)
    assert restored.density == density
    assert restored.theme == theme


def test_external_density_change_updates_all_open_selectors_without_feedback(terminal, monkeypatch):
    app, manager, settings, create_page = terminal
    first, first_presenter = create_page()
    second, second_presenter = create_page()
    setter = MagicMock(wraps=manager.set_density)
    monkeypatch.setattr(manager, "set_density", setter)
    first_changes = QSignalSpy(first.density_selector.currentIndexChanged)
    second_changes = QSignalSpy(second.density_selector.currentIndexChanged)
    density_changes = QSignalSpy(manager.density_changed)
    presenter_calls = (list(first_presenter.mock_calls), list(second_presenter.mock_calls))

    manager.set_density("touch", app=app)
    app.processEvents()

    assert first.density_selector.currentData() == "touch"
    assert second.density_selector.currentData() == "touch"
    assert len(first_changes) == len(second_changes) == 0
    assert list(density_changes) == [["touch"]]
    assert setter.call_count == 1
    assert settings.value("appearance/density") == "touch"
    assert (first_presenter.mock_calls, second_presenter.mock_calls) == presenter_calls


def test_density_selection_synchronizes_other_page_without_reapplying(terminal, monkeypatch):
    app, manager, _, create_page = terminal
    first, _ = create_page()
    second, _ = create_page()
    setter = MagicMock(wraps=manager.set_density)
    monkeypatch.setattr(manager, "set_density", setter)
    second_changes = QSignalSpy(second.density_selector.currentIndexChanged)
    density_changes = QSignalSpy(manager.density_changed)

    first.density_selector.setCurrentIndex(first.density_selector.findData("compact"))
    app.processEvents()

    assert second.density_selector.currentData() == "compact"
    assert len(second_changes) == 0
    assert list(density_changes) == [["compact"]]
    setter.assert_called_once_with("compact", app=app)
