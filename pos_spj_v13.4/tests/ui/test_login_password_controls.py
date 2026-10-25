"""Password visibility and touch entry preserve the login credential exactly."""
import os
from pathlib import Path
import string
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QPoint, QRect, QSettings, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QLineEdit

from frontend.desktop.auth.login_window import LoginWindow
from frontend.desktop.themes.theme_manager import ThemeManager


@pytest.fixture
def login(qt_font_resources, ui_tmp_path, monkeypatch):
    settings = QSettings(str(ui_tmp_path / 'login.ini'), QSettings.IniFormat)
    manager = ThemeManager(settings)
    monkeypatch.setattr(ThemeManager, '_instance', manager)
    # Do not inherit keyboard preferences from the developer's terminal.
    monkeypatch.setattr('frontend.desktop.components.virtual_keyboard.QSettings', lambda *args: settings)
    manager.apply(qt_font_resources, 'light', density='comfortable')
    authenticate = Mock()
    window = LoginWindow(
        authenticate_use_case=authenticate, begin_recovery_use_case=Mock(),
        complete_recovery_use_case=Mock(), workstation_id='test-terminal',
        installation_summary_query=SimpleNamespace(get_summary=lambda: SimpleNamespace(
            company_name='Empresa de prueba', branch_name='Sucursal de prueba')),
    )
    window.show()
    for _ in range(4):
        qt_font_resources.processEvents()
    yield window, authenticate, manager, qt_font_resources
    sip.delete(window)


def test_visibility_toggle_preserves_text_cursor_and_selection(login):
    window, _, _, app = login
    password = window._password_input
    password.setText('  Clave-9!  ')
    password.setSelection(2, 5)
    assert password.echoMode() == QLineEdit.Password
    window._show_password.click()
    assert password.echoMode() == QLineEdit.Normal
    assert password.selectedText() == 'Clave'
    window._show_password.click()
    assert password.echoMode() == QLineEdit.Password
    assert password.value() == '  Clave-9!  '
    window._show_password.setFocus()
    QTest.keyClick(window._show_password, Qt.Key_Space)
    assert password.echoMode() == QLineEdit.Normal
    app.processEvents()


def test_keyboard_enters_password_and_login_submits_it_once(login):
    window, authenticate, _, app = login
    password = window._password_input
    window._username_input.setText('operador')
    password.keyboard_action().trigger()
    keyboard = password._keyboard_controller.keyboard
    assert keyboard.isVisible()
    keyboard.keys['Espacio'].click()
    keyboard.keys['Mayús'].click()
    keyboard.keys['c'].click()
    keyboard.keys['Mayús'].click()
    for character in 'lave9':
        keyboard.keys[character].click()
    keyboard.keys['Símbolos'].click()
    keyboard.keys['!'].click()
    keyboard.keys['Espacio'].click()
    assert password.value() == ' Clave9! '
    assert password.echoMode() == QLineEdit.Password
    window._show_password.click()
    window._login_btn.click()
    app.processEvents()
    authenticate.execute.assert_called_once_with(
        username='operador', password=' Clave9! ', workstation_id='test-terminal')
    assert password.echoMode() == QLineEdit.Password
    assert not keyboard.isVisible()


def test_symbol_bank_covers_punctuation_and_returns_to_letters(login):
    window, _, _, _ = login
    field = window._password_input
    field.keyboard_action().trigger()
    keyboard = field._keyboard_controller.keyboard
    keyboard.keys['Símbolos'].click()
    assert keyboard.keys['&'].text() == '&&'
    assert keyboard.keys['&'].accessibleName() == '&'
    for character in string.punctuation:
        keyboard.keys[character].click()
    assert field.value() == string.punctuation
    keyboard.backspace()
    assert field.value() == string.punctuation[:-1]
    field.selectAll()
    keyboard.keys['Símbolos'].click()
    keyboard.keys['ñ'].click()
    assert field.value() == 'ñ'


def test_error_and_reopening_remask_password(login):
    window, authenticate, _, app = login
    from backend.security.authentication.errors import AuthenticationFailedError
    authenticate.execute.side_effect = AuthenticationFailedError('Datos incorrectos')
    window._username_input.setText('operador')
    window._password_input.setText('Clave9!')
    window._show_password.click()
    window._login_btn.click()
    assert window._password_input.text() == ''
    assert not window._show_password.isChecked()
    assert window._password_input.echoMode() == QLineEdit.Password
    window._show_password.click()
    window.hide()
    window.show()
    app.processEvents()
    assert not window._show_password.isChecked()
    assert window._password_input.echoMode() == QLineEdit.Password


@pytest.mark.parametrize('theme', ['light', 'dark'])
@pytest.mark.parametrize('density', ['compact', 'comfortable', 'touch'])
def test_password_controls_fit_and_follow_theme_density(login, theme, density):
    window, _, manager, app = login
    manager.apply(app, theme, density=density)
    for _ in range(4):
        app.processEvents()
    field = window._password_input
    button = field._keyboard_controller.button
    assert button.isVisible()
    assert field.rect().contains(button.geometry())
    assert not button.icon().isNull()
    assert window._show_password.isVisible()
    for widget in (field, window._show_password, window._login_btn):
        assert window.rect().contains(QRect(widget.mapTo(window, QPoint()), widget.size()))
    directory = os.environ.get('SPJ_LOGIN_CONTROL_ARTIFACTS')
    if directory:
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        assert window.grab().save(str(target / f'login-{theme}-{density}.png'))
        field.keyboard_action().trigger()
        keyboard = field._keyboard_controller.keyboard
        keyboard.keys['Símbolos'].click()
        for _ in range(4):
            app.processEvents()
        assert keyboard.grab().save(str(target / f'keyboard-{theme}-{density}.png'))
