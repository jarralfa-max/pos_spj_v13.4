"""The user menu exposes current identity and the existing logout transition."""
from dataclasses import replace
import os
from pathlib import Path

import pytest
from PyQt5.QtCore import QPoint, QRect, QSettings, Qt, QTimer
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QLabel, QMessageBox

from frontend.desktop.shell.application_shell.top_bar import TopBar
from frontend.desktop.shell.application_shell.application_window import ApplicationWindow
from frontend.desktop.shell.router.desktop_router import DesktopRouter
from frontend.desktop.shell.routing.offline_policy import OfflinePolicy
from frontend.desktop.shell.routing.route_definition import RouteDefinition
from frontend.desktop.shell.routing.route_registry import RouteRegistry
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry
from tests.ui.shell.conftest import make_context
from tests.ui.shell.test_application_window import _window


def test_user_menu_reuses_logout_action_and_is_keyboard_accessible(app):
    bar = TopBar()
    bar.set_context(make_context(user_name="Ana Ruiz"))
    bar.show()
    app.processEvents()
    assert bar._user_button.menu() is bar.user_menu
    assert bar.logout_action in bar.user_menu.actions()
    assert bar.logout_action in bar.file_menu.actions()
    assert "Ana Ruiz" in bar._user_button.accessibleName()
    bar.activateWindow()
    bar._user_button.setFocus()
    app.processEvents()
    opened = []

    def dismiss_menu():
        opened.append(bar.user_menu.isVisible())
        QTest.keyClick(bar.user_menu, Qt.Key_Escape)

    QTimer.singleShot(100, dismiss_menu)
    QTest.keyClick(bar._user_button, Qt.Key_Space)
    QTest.qWait(150)
    assert opened == [True]
    assert not bar.user_menu.isVisible()
    bar.close()


def test_profile_uses_current_context_and_plain_text(monkeypatch):
    from frontend.desktop.shell.application_shell.user_profile_dialog import UserProfileDialog

    window = _window()
    current = replace(window.router.current_context, user_name="Ana <b>Ruiz</b>",
                      branch_name="Sucursal Norte", roles=("admin", "Auditor"))
    window.update_context(current)
    seen = []

    def inspect(dialog):
        assert isinstance(dialog, UserProfileDialog)
        labels = dialog.findChildren(QLabel)
        texts = [label.text() for label in labels]
        assert current.user_name in texts
        assert current.branch_name in texts
        assert "Administrador, Auditor" in texts
        assert "Conectado" in texts
        assert all(label.textFormat() == Qt.PlainText for label in labels
                   if label.text() in (current.user_name, current.branch_name))
        seen.append(dialog)
        return 0

    monkeypatch.setattr(UserProfileDialog, "exec_", inspect)
    window.top_bar.profile_action.trigger()
    assert len(seen) == 1


@pytest.mark.parametrize("answer,expected", [(QMessageBox.Yes, ["logout"]), (QMessageBox.No, [])])
def test_logout_from_user_menu_confirms_without_closing_window(monkeypatch, answer, expected):
    window = _window()
    window.show()
    calls = []
    window.logout_requested.connect(lambda: calls.append("logout"))

    def confirm(*args):
        assert args[-1] == QMessageBox.No
        return answer

    monkeypatch.setattr(QMessageBox, "question", confirm)
    action = next(action for action in window.top_bar.user_menu.actions() if action.text() == "Cerrar sesión")
    action.trigger()
    assert calls == expected
    assert window.isVisible()
    window.close()


def test_navigation_keeps_top_and_bottom_connectivity_consistent():
    routes = RouteRegistry()
    for route_id, policy in [("reduced", OfflinePolicy.DEGRADED_OFFLINE),
                             ("local", OfflinePolicy.AVAILABLE_OFFLINE)]:
        routes.register(RouteDefinition(route_id=route_id, module_id="test", title=route_id,
                                        view_factory_id="view", offline_policy=policy))
    factories = ViewFactoryRegistry()
    factories.register("view", lambda: QLabel("Contenido"))
    window = ApplicationWindow(router=DesktopRouter(route_registry=routes,
        view_factory_registry=factories, initial_context=make_context(offline_status="OFFLINE")))
    window.navigate("reduced")
    assert window.top_bar.session_text == window.status_bar.connectivity_text == "Conexión limitada"
    window.navigate("local")
    assert window.top_bar.session_text == window.status_bar.connectivity_text == "Sin conexión"
    window.update_context(replace(window.router.current_context, offline_status="ONLINE"))
    assert window.top_bar.session_text == "Conectado"


@pytest.mark.parametrize("state,label", [("locked", "Sesión bloqueada"), ("expiring", "Sesión próxima a vencer")])
def test_connectivity_updates_do_not_erase_session_state(state, label):
    bar = TopBar()
    context = make_context()
    bar.set_context(context)
    bar.set_session_state(state)
    bar.set_context(replace(context, offline_status="OFFLINE"))
    bar.set_offline_status("OFFLINE", degraded=True)
    assert bar.session_text == label
    # A different authenticated session must not inherit the old warning.
    bar.set_context(replace(context, session_id="019a05f0-0000-7000-8000-000000000002"))
    assert bar.session_text == "Conectado"


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("density", ["compact", "comfortable", "touch"])
def test_user_controls_fit_theme_and_density(qt_font_resources, ui_tmp_path, monkeypatch, theme, density):
    from PyQt5 import sip
    from frontend.desktop.shell.application_shell.user_profile_dialog import UserProfileDialog
    from frontend.desktop.themes.theme_manager import ThemeManager

    app = qt_font_resources
    manager = ThemeManager(QSettings(str(ui_tmp_path / "session.ini"), QSettings.IniFormat))
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(app, theme, density=density)
    window = _window(make_context(user_name="Ana María Rodríguez Hernández",
                                  branch_name="Sucursal San Juan de los Lagos"))
    window.resize(1024, 768)
    window.show()
    window.navigate("sales.pos")
    profile = UserProfileDialog(window.router.current_context,
                               session_text=window.top_bar.session_text, parent=window)
    try:
        for _ in range(4):
            app.processEvents()
        bar = window.top_bar
        for control in (bar._user_button, bar._settings_button, bar._notifications_button, bar._file_button):
            assert bar.rect().contains(QRect(control.mapTo(bar, QPoint()), control.size()))
        assert bar._user_button.rect().contains(bar._context_label.geometry())
        assert bar._user_button.rect().contains(bar._session_badge.geometry())
        artifacts = os.environ.get("SPJ_SESSION_CONTROL_ARTIFACTS")
        if artifacts:
            target = Path(artifacts)
            target.mkdir(parents=True, exist_ok=True)
            assert window.grab().save(str(target / f"shell-{theme}-{density}.png"))
        profile.show()
        for _ in range(4):
            app.processEvents()
        assert profile.available_geometry().contains(profile.frameGeometry())
        if artifacts:
            assert profile.grab().save(str(target / f"profile-{theme}-{density}.png"))
    finally:
        sip.delete(profile)
        sip.delete(window)
