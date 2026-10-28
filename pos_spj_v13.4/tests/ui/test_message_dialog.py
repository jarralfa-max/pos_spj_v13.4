"""MessageDialog keeps QMessageBox's contract inside the StandardDialog shell."""
import pytest
from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QDialogButtonBox, QLabel, QMessageBox

from frontend.desktop.components.dialogs import MessageDialog, StandardDialog
from tests.ui.test_standard_window_geometry import settle

M = QMessageBox
# Measured on a real Qt 5 QMessageBox (windows platform; it crashes when shown
# under offscreen): (buttons, explicit default, result of Return, of Escape).
_QMESSAGEBOX_REFERENCE = [
    (M.Ok, M.NoButton, M.Ok, M.Ok),
    (M.Ok, M.Ok, M.Ok, M.Ok),
    (M.Yes | M.No, M.NoButton, M.Yes, M.No),
    (M.Yes | M.No, M.No, M.No, M.No),
    (M.Ok | M.Cancel, M.NoButton, M.Ok, M.Cancel),
    (M.Ok | M.Cancel, M.Cancel, M.Cancel, M.Cancel),
    (M.Yes | M.No | M.Cancel, M.NoButton, M.Yes, M.Cancel),
    (M.Yes | M.No | M.Cancel, M.Cancel, M.Cancel, M.Cancel),
    (M.Save | M.Discard | M.Cancel, M.NoButton, M.Save, M.Cancel),
    (M.Save | M.Discard | M.Cancel, M.Cancel, M.Cancel, M.Cancel),
    (M.Retry | M.Close, M.NoButton, M.Retry, M.Close),
    (M.Retry | M.Close, M.Close, M.Close, M.Close),
    (M.Yes | M.Save, M.NoButton, M.Yes, M.NoButton),
    (M.Yes | M.Save, M.Save, M.Save, M.NoButton),
]


@pytest.mark.parametrize("buttons,default,on_return,on_escape", _QMESSAGEBOX_REFERENCE)
@pytest.mark.parametrize("key", [Qt.Key_Return, Qt.Key_Escape])
def test_default_and_escape_resolution_matches_qmessagebox(qt_font_resources, monkeypatch, buttons,
                                                           default, on_return, on_escape, key):
    app = qt_font_resources

    def interact(dialog):
        dialog.show()
        settle(app)
        QTest.keyClick(dialog, key)
        settle(app)
        result = dialog.result()
        dialog.close()
        return result

    monkeypatch.setattr(MessageDialog, "exec_", interact)
    choice = MessageDialog.question(None, "t", "m", buttons, default)
    assert choice == (on_return if key == Qt.Key_Return else on_escape)


def test_escape_without_escape_button_keeps_dialog_open(qt_font_resources):
    dialog = MessageDialog(None, level="question", title="t", text="m",
                           buttons=QMessageBox.Yes | QMessageBox.Save)
    dialog.show()
    settle(qt_font_resources)
    QTest.keyClick(dialog, Qt.Key_Escape)
    settle(qt_font_resources)
    assert dialog.isVisible()
    dialog.close()  # the window's close button is ignored as well
    settle(qt_font_resources)
    assert dialog.isVisible()
    assert dialog.clickedButton() is None
    # The unattended UI self-test dismisses modals this way; it must still work.
    dialog.reject()
    settle(qt_font_resources)
    assert not dialog.isVisible()
    assert dialog.standardButton(dialog.clickedButton()) == QMessageBox.NoButton
    dialog.deleteLater()


def test_constants_and_return_values_are_qmessagebox_values():
    assert MessageDialog.Yes == QMessageBox.Yes
    assert MessageDialog.No == QMessageBox.No
    assert MessageDialog.Ok == QMessageBox.Ok
    assert int(MessageDialog.Yes | MessageDialog.No) == int(QMessageBox.Yes | QMessageBox.No)
    assert MessageDialog.AcceptRole == QMessageBox.AcceptRole


@pytest.mark.parametrize("level,icon_state", [("information", "info"), ("question", "info"),
                                               ("warning", "warning"), ("critical", "danger")])
def test_message_uses_standard_shell_spanish_buttons_and_plain_text(qt_font_resources, level, icon_state):
    text = "Cantidad <b>no</b> válida & sin <br> formato"
    dialog = MessageDialog(None, level=level, title="Aviso", text=text,
                           buttons=QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
    try:
        assert isinstance(dialog, StandardDialog)
        assert not dialog.windowIcon().isNull()
        assert dialog.windowTitle() == "Aviso"
        assert dialog.property("messageLevel") == level
        label = dialog.findChild(QLabel, "messageDialogText")
        assert label.textFormat() == Qt.PlainText and label.text() == text
        icon = dialog.findChild(QLabel, "messageDialogIcon")
        assert icon.property("icon") and icon.pixmap() is not None
        assert icon.accessibleName()  # level is not represented only by color
        assert dialog.accessibleName().endswith(": Aviso")
        box = dialog.findChild(QDialogButtonBox)
        assert sorted(b.text() for b in box.buttons()) == ["Cancelar", "No", "Sí"]
        assert not dialog.viewport.isAncestorOf(box)
    finally:
        dialog.deleteLater()


def test_custom_buttons_keep_clicked_button_contract(qt_font_resources, monkeypatch):
    dialog = MessageDialog(None, level="critical", title="Recuperación", text="m",
                           buttons=QMessageBox.NoButton)
    recover = dialog.addButton("Recuperar", MessageDialog.AcceptRole)
    leave = dialog.addButton("Salir", MessageDialog.RejectRole)
    dialog.show()
    settle(qt_font_resources)
    QTest.keyClick(dialog, Qt.Key_Escape)
    assert dialog.clickedButton() is leave
    assert recover.isDefault()
    dialog.deleteLater()


def test_long_message_stays_inside_the_monitor_with_reachable_buttons(qt_font_resources, monkeypatch):
    app = qt_font_resources
    dialog = MessageDialog(None, level="warning", title="Detalle",
                           text="\n".join(f"Renglón {i} del detalle" for i in range(200)),
                           buttons=QMessageBox.Ok | QMessageBox.Cancel)
    monkeypatch.setattr(dialog, "available_geometry", lambda: QRect(0, 0, 640, 480))
    dialog.show()
    settle(app)
    try:
        assert dialog.available_geometry().contains(dialog.frameGeometry())
        box = dialog.findChild(QDialogButtonBox)
        for button in box.buttons():
            assert dialog.rect().contains(QRect(button.mapTo(dialog, QPoint()), button.size()))
    finally:
        dialog.close()
        dialog.deleteLater()
