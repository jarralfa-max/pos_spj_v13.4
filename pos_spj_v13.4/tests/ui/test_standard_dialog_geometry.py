"""Dialog monitor selection, overflow limits and repeated show lifecycle."""
import pytest
from PyQt5 import sip
from PyQt5.QtCore import QRect, QSettings, QSize
from PyQt5.QtWidgets import QApplication, QLabel, QWidget

from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.themes.theme_manager import ThemeManager
from tests.ui.test_standard_window_geometry import DesktopScreen, settle


@pytest.fixture
def dialog_desktop(qt_font_resources, ui_tmp_path, monkeypatch):
    app = qt_font_resources
    manager = ThemeManager(QSettings(str(ui_tmp_path / "dialogs.ini"), QSettings.IniFormat))
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(app, "light", density="comfortable")
    primary = DesktopScreen(QRect(0, 0, 1280, 720))
    secondary = DesktopScreen(QRect(-1440, 0, 1440, 900))
    monkeypatch.setattr(QApplication, "primaryScreen", lambda: primary)
    monkeypatch.setattr(QApplication, "screens", lambda: [primary, secondary])
    monkeypatch.setattr(StandardDialog, "screen", lambda self: primary)
    parent = QWidget()
    monkeypatch.setattr(parent, "screen", lambda: primary)
    dialog = StandardDialog(parent, title="Captura de prueba", width=600)
    field = StandardLineEdit(keyboard_enabled=False)
    field.setText("Captura pendiente")
    dialog.content_layout().addWidget(field)
    dialog.add_button_box(ok_text="Guardar")
    yield app, primary, secondary, dialog, field
    sip.delete(parent)


def test_moved_dialog_uses_its_own_monitor_and_disconnects_parent_screen(dialog_desktop, monkeypatch):
    app, primary, secondary, dialog, field = dialog_desktop
    dialog.show()
    settle(app)
    monkeypatch.setattr(dialog, "screen", lambda: secondary)
    dialog.move(-1400, 40)
    handle = dialog.windowHandle()
    handle.screenChanged.emit(handle.screen())
    settle(app)
    assert dialog.available_geometry() == secondary.availableGeometry()
    assert secondary.availableGeometry().contains(dialog.frameGeometry())
    saved = dialog.geometry()
    primary.change_available_area(QRect(0, 0, 600, 400))
    settle(app)
    assert dialog.geometry() == saved
    secondary.change_available_area(QRect(-1440, 0, 800, 600))
    settle(app)
    assert secondary.availableGeometry().contains(dialog.frameGeometry())
    assert field.text() == "Captura pendiente"


def test_explicit_minimum_yields_to_small_screen_and_recovers(dialog_desktop):
    app, primary, _, dialog, _ = dialog_desktop
    dialog.setMinimumSize(900, 760)
    primary.geometry = QRect(0, 0, 800, 600)
    dialog.show()
    settle(app)
    assert primary.availableGeometry().contains(dialog.frameGeometry())
    assert dialog.minimumWidth() < 900 and dialog.minimumHeight() < 760
    primary.change_available_area(QRect(0, 0, 1600, 1000))
    settle(app)
    assert dialog.minimumSize() == QSize(900, 760)
    assert primary.availableGeometry().contains(dialog.frameGeometry())


def test_reopening_preserves_user_size_and_capture(dialog_desktop):
    app, _, _, dialog, field = dialog_desktop
    dialog.show()
    settle(app)
    dialog.resize(850, 500)
    settle(app)
    saved = dialog.size()
    dialog.hide()
    dialog.show()
    settle(app)
    assert dialog.size() == saved
    assert field.text() == "Captura pendiente"


def test_lost_dialog_moves_back_inside_available_screen(dialog_desktop):
    app, primary, _, dialog, _ = dialog_desktop
    dialog.show()
    settle(app)
    dialog.move(5000, 5000)
    settle(app)
    assert primary.availableGeometry().contains(dialog.frameGeometry())


def test_crossing_monitor_edge_is_not_undone_before_screen_change(dialog_desktop):
    app, primary, secondary, dialog, _ = dialog_desktop
    dialog.show()
    settle(app)
    dialog.move(-100, 40)
    settle(app)
    frame = dialog.frameGeometry()
    assert primary.availableGeometry().contains(frame.center())
    assert secondary.availableGeometry().intersects(frame)


def test_validation_callback_does_not_accept_before_validation(dialog_desktop):
    app, _, _, dialog, _ = dialog_desktop
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QDialogButtonBox

    attempts = []
    box = dialog.add_button_box(on_accept=lambda: attempts.append("invalid"))
    dialog.show()
    settle(app)
    QTest.mouseClick(box.button(QDialogButtonBox.Ok), Qt.LeftButton)
    assert attempts == ["invalid"]
    assert dialog.isVisible()


def test_changing_window_title_updates_visible_heading(dialog_desktop):
    app, _, _, dialog, _ = dialog_desktop
    dialog.show()
    settle(app)
    dialog.setWindowTitle("Editar precio de producto")
    settle(app)
    headings = [label for label in dialog.findChildren(QLabel)
                if label.property("role") == "dialogTitle"]
    assert len(headings) == 1
    assert headings[0].text() == dialog.windowTitle()
    assert headings[0].isVisible()
    dialog.setWindowTitle("")
    assert not headings[0].isVisible()
