"""The keyboard opener remains a usable target without covering input text."""
import pytest
from PyQt5 import sip
from PyQt5.QtCore import QPoint, QRect, QSettings, Qt
from PyQt5.QtGui import QIntValidator
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QAbstractButton, QLineEdit, QVBoxLayout, QWidget

from frontend.desktop.components import IntegerInput, MoneyInput, StandardLineEdit
from frontend.desktop.components.virtual_keyboard import KeyboardAwareInput
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import density_metrics


@pytest.fixture
def terminal(qt_font_resources, ui_tmp_path, monkeypatch):
    manager = ThemeManager(QSettings(str(ui_tmp_path / "appearance.ini"), QSettings.IniFormat))
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(qt_font_resources, "light", density="comfortable")
    settings = QSettings(str(ui_tmp_path / "keyboard.ini"), QSettings.IniFormat)
    host = QWidget()
    QVBoxLayout(host)
    yield qt_font_resources, manager, settings, host
    sip.delete(host)


def _opener(control):
    buttons = [button for button in control.findChildren(QAbstractButton)
               if button.toolTip().startswith("Mostrar teclado") and not button.isHidden()]
    assert len(buttons) == 1
    return buttons[0]


def _rect_in(widget, parent):
    return QRect(widget.mapTo(parent, QPoint()), widget.size())


@pytest.mark.parametrize("factory", [StandardLineEdit, IntegerInput, MoneyInput])
@pytest.mark.parametrize("direction", [Qt.LeftToRight, Qt.RightToLeft])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_keyboard_target_round_trip_fits_control_and_keeps_text_clear(terminal, factory, direction, theme):
    app, manager, _, host = terminal
    manager.apply(app, theme, density="comfortable")
    control = factory()
    line = control if isinstance(control, QLineEdit) else control.lineEdit()
    control.setLayoutDirection(direction)
    line.setClearButtonEnabled(True)
    if isinstance(control, QLineEdit):
        line.setText("123456789012345678901234567890123456789012345678901234567890")
    else:
        control.setValue(12345)
    line.setAlignment(Qt.AlignRight if direction == Qt.RightToLeft else Qt.AlignLeft)
    original = line.text()
    host.layout().addWidget(control)
    host.resize(400, 140)
    host.show()
    host.activateWindow()
    line.setFocus()
    for density in ("comfortable", "touch", "compact", "comfortable"):
        manager.set_density(density, app=app)
        for _ in range(4):
            app.processEvents()
        opener = _opener(control)
        minimum = density_metrics(density).icon_button_size
        assert opener.width() >= minimum
        assert opener.height() >= minimum
        assert control.rect().contains(_rect_in(opener, control))
        assert opener.visibleRegion().boundingRect() == opener.rect()
        assert opener.focusPolicy() == Qt.NoFocus
        line.setCursorPosition(len(line.text()))
        app.processEvents()
        cursor = QRect(line.inputMethodQuery(Qt.ImCursorRectangle))
        cursor.moveTopLeft(line.mapTo(control, cursor.topLeft()))
        assert not cursor.intersects(_rect_in(opener, control))
        assert line.text() == original
        assert line.styleSheet() == opener.styleSheet() == ""


@pytest.mark.parametrize("direction", [Qt.LeftToRight, Qt.RightToLeft])
def test_keyboard_mode_and_action_removal_restore_original_text_margins(terminal, direction):
    app, manager, settings, host = terminal
    line = QLineEdit()
    line.setTextMargins(7, 3, 11, 4)
    margins = line.textMargins()
    line.setLayoutDirection(direction)
    controller = KeyboardAwareInput(line, settings=settings)
    host.layout().addWidget(line)
    host.show()
    for density in ("touch", "compact", "comfortable"):
        manager.set_density(density, app=app)
        app.processEvents()
        opener = _opener(line)
        active = line.textMargins()
        assert active != margins
        controller.set_mode("disabled", persist=False)
        app.processEvents()
        assert opener.isHidden()
        assert line.textMargins() == margins
        controller.set_mode("icon_only", persist=False)
        app.processEvents()
        assert line.textMargins() == active
    line.removeAction(controller.action)
    app.processEvents()
    assert line.textMargins() == margins
    assert opener.isHidden() or sip.isdeleted(opener)


def test_clicking_edge_of_touch_target_keeps_selection_and_existing_validator(terminal, monkeypatch):
    from frontend.desktop.components.virtual_keyboard import VirtualKeyboard
    shown = []
    # Offscreen activates Qt.Tool windows despite WindowDoesNotAcceptFocus.
    # Verify the button's open request without that window-manager side effect.
    monkeypatch.setattr(VirtualKeyboard, "show", lambda keyboard: shown.append(keyboard))
    app, manager, settings, host = terminal
    manager.set_density("touch", app=app)
    line = QLineEdit()
    line.setValidator(QIntValidator(0, 999, line))
    controller = KeyboardAwareInput(line, input_mode="integer", settings=settings)
    host.layout().addWidget(line)
    host.show()
    host.activateWindow()
    line.setText("12")
    line.setFocus()
    line.selectAll()
    app.processEvents()
    opener = _opener(line)
    assert opener.width() >= 48
    QTest.mouseClick(opener, Qt.LeftButton, pos=QPoint(2, opener.height() // 2))
    app.processEvents()
    assert shown == [controller.keyboard] and controller.keyboard is not None
    assert line.hasFocus()
    assert line.selectedText() == "12"
    controller.keyboard.press_key("8")
    controller.keyboard.insert_text("x")
    assert line.text() == "8"


def test_standard_input_can_remove_and_reattach_keyboard_without_duplicate_targets(terminal):
    app, manager, _, host = terminal
    manager.set_density("touch", app=app)
    line = StandardLineEdit(keyboard_enabled=False)
    margins = line.textMargins()
    host.layout().addWidget(line)
    host.show()
    for _ in range(3):
        line.set_keyboard_enabled(True)
        app.processEvents()
        assert _opener(line).width() >= 48
        assert len(line.actions()) == 1
        line.set_keyboard_enabled(False)
        app.processEvents()
        assert line.textMargins() == margins
        assert not [button for button in line.findChildren(QAbstractButton) if not button.isHidden()]
