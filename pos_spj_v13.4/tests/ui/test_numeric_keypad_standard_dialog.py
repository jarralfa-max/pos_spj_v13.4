"""Numeric capture used by POS keeps its data and actions inside the monitor."""
import pytest
from PyQt5 import sip
from PyQt5.QtCore import QPoint, QRect, QSettings, Qt
from PyQt5.QtTest import QTest

from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.components.numeric_keypad_dialog import NumericKeypadDialog
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import density_metrics
from tests.ui.test_standard_window_geometry import settle


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("density", ["compact", "comfortable", "touch"])
def test_numeric_capture_fits_with_keyboard_and_preserves_value(
        qt_font_resources, ui_tmp_path, monkeypatch, theme, density):
    app = qt_font_resources
    manager = ThemeManager(QSettings(str(ui_tmp_path / "numeric.ini"), QSettings.IniFormat))
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(app, theme, density=density)
    dialog = NumericKeypadDialog(titulo="Capturar peso", decimals=3, inicial=12.5, unidad="kg")
    try:
        assert isinstance(dialog, StandardDialog)
        monkeypatch.setattr(dialog, "available_geometry", lambda: QRect(0, 0, 640, 480))
        dialog.show()
        settle(app)
        assert not dialog.windowIcon().isNull()
        for expanded in (True, False, True):
            dialog._btn_toggle.setChecked(expanded)
            settle(app)
            assert dialog.valor() == 12.5
            assert dialog.available_geometry().contains(dialog.frameGeometry())
            for button in (dialog.btn_ok, dialog.btn_cancel):
                assert not dialog.viewport.isAncestorOf(button)
                assert dialog.rect().contains(QRect(button.mapTo(dialog, QPoint()), button.size()))
                assert button.height() >= density_metrics(density).button_height
                assert not button.visibleRegion().isEmpty()
        QTest.keyClick(dialog, Qt.Key_Return)
        assert dialog.result() == dialog.Accepted
        assert dialog.valor() == 12.5
    finally:
        sip.delete(dialog)


def test_numeric_invalid_enter_stays_open_and_escape_cancels(qt_font_resources):
    app = qt_font_resources
    dialog = NumericKeypadDialog()
    try:
        dialog.show()
        settle(app)
        QTest.keyClick(dialog, Qt.Key_Return)
        assert dialog.isVisible()
        assert dialog.valor() == 0
        QTest.keyClick(dialog, Qt.Key_Escape)
        assert not dialog.isVisible()
        assert dialog.result() == dialog.Rejected
    finally:
        sip.delete(dialog)
