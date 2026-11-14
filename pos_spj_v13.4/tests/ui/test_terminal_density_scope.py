"""SDLC-UI-007 — la densidad se fija por terminal, no por usuario de Windows.

Decisión del responsable (2026-11-02): la densidad TOUCH va por terminal (todo
táctil en esa PC) y aplica a todas las pantallas de operación. La terminal guarda
su densidad en la carpeta de datos de la estación (en instalación por máquina,
compartida por todos los usuarios de Windows); el tema sigue siendo del usuario.
"""
from __future__ import annotations

import pytest
from PyQt5.QtCore import QSettings

from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import density_metrics


@pytest.fixture
def stores(ui_tmp_path):
    user = QSettings(str(ui_tmp_path / "user.ini"), QSettings.IniFormat)
    terminal = QSettings(str(ui_tmp_path / "terminal.ini"), QSettings.IniFormat)
    return user, terminal


@pytest.fixture
def restore_app_state(qt_font_resources, monkeypatch):
    previous = ThemeManager._instance
    yield qt_font_resources
    monkeypatch.setattr(ThemeManager, "_instance", previous)
    if previous is not None:
        previous.apply(qt_font_resources, "light", density="comfortable")


def test_density_is_read_from_the_terminal_store_not_the_windows_user(stores, restore_app_state):
    app = restore_app_state
    user, terminal = stores
    user.setValue("appearance/density", "compact")
    terminal.setValue("appearance/density", "touch")
    manager = ThemeManager(user, terminal_settings=terminal)
    manager.restore(app)
    assert manager.density == "touch"


def test_density_change_is_persisted_for_the_terminal(stores, restore_app_state):
    app = restore_app_state
    user, terminal = stores
    manager = ThemeManager(user, terminal_settings=terminal)
    manager.restore(app)
    manager.apply(app, "dark", density="touch")
    assert terminal.value("appearance/density") == "touch"
    assert user.value("appearance/density") is None
    assert user.value("appearance/theme") == "dark"          # theme stays per user


def test_unconfigured_terminal_adopts_the_previous_user_choice_once(stores, restore_app_state):
    app = restore_app_state
    user, terminal = stores
    user.setValue("appearance/density", "compact")
    manager = ThemeManager(user, terminal_settings=terminal, touch_probe=lambda: True)
    manager.restore(app)
    assert manager.density == "compact"
    assert terminal.value("appearance/density") == "compact"


@pytest.mark.parametrize("touchscreen,expected", [(True, "touch"), (False, "comfortable")])
def test_unconfigured_terminal_defaults_to_touch_only_on_a_touchscreen(
        stores, restore_app_state, touchscreen, expected):
    app = restore_app_state
    user, terminal = stores
    manager = ThemeManager(user, terminal_settings=terminal, touch_probe=lambda: touchscreen)
    manager.restore(app)
    assert manager.density == expected


def test_runtime_terminal_store_lives_in_the_station_data_root(ui_tmp_path, monkeypatch):
    monkeypatch.setenv("SPJ_APP_DATA_DIR", str(ui_tmp_path / "station"))
    store = ThemeManager._default_terminal_settings()
    assert store is not None
    assert (ui_tmp_path / "station").resolve() in __import__("pathlib").Path(store.fileName()).resolve().parents


def test_pos_controls_are_touch_sized_on_a_touch_terminal(stores, restore_app_state, monkeypatch):
    from PyQt5.QtWidgets import QLineEdit, QPushButton
    from backend.application.sales.permissions import SalesPermissions
    from frontend.desktop.modules.sales_pos.sales_pos_presenter import SalesPosPresenter
    from frontend.desktop.modules.sales_pos.sales_pos_workspace import SalesPosWorkspace

    class _Session:
        user_id, active_branch_id, is_active = "cashier-1", "branch-1", True

        def tiene_permiso(self, _code):
            return True

    app = restore_app_state
    user, terminal = stores
    terminal.setValue("appearance/density", "touch")
    manager = ThemeManager(user, terminal_settings=terminal)
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.restore(app)

    workspace = SalesPosWorkspace(SalesPosPresenter(session_context=_Session()))
    try:
        workspace.resize(1366, 768)
        workspace.show()
        app.processEvents()
        touch = density_metrics("touch")
        buttons = [b for b in workspace.findChildren(QPushButton) if b.isVisible()]
        inputs = [e for e in workspace.findChildren(QLineEdit) if e.isVisible()]
        assert buttons and inputs
        assert min(b.height() for b in buttons) >= touch.button_height - 4
        assert min(e.height() for e in inputs) >= touch.input_height
    finally:
        workspace.close()
        workspace.deleteLater()
