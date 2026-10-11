"""Existing module action wiring survives adoption of the fixed dialog footer."""
import pytest
from PyQt5 import sip
from PyQt5.QtCore import QPoint, QRect, QSettings, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QDialogButtonBox, QHBoxLayout, QPushButton, QWidget

from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import density_metrics
from tests.ui.test_standard_window_geometry import settle


@pytest.mark.parametrize("kind", ["box", "container", "button"])
@pytest.mark.parametrize("density", ["compact", "comfortable", "touch"])
def test_existing_footer_preserves_wiring_and_stays_accessible(
        qt_font_resources, ui_tmp_path, monkeypatch, kind, density):
    app = qt_font_resources
    manager = ThemeManager(QSettings(str(ui_tmp_path / "footer.ini"), QSettings.IniFormat))
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(app, "dark", density=density)
    dialog = StandardDialog(title="Acciones del módulo")
    monkeypatch.setattr(dialog, "available_geometry", lambda: QRect(0, 0, 640, 480))
    for index in range(25):
        field = StandardLineEdit(keyboard_enabled=False)
        field.setText(str(index))
        dialog.content_layout().addWidget(field)
    attempts = []
    if kind == "box":
        footer = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        save = footer.button(QDialogButtonBox.Save)
        footer.accepted.connect(lambda: attempts.append("validate"))
        footer.rejected.connect(dialog.reject)
    else:
        save = QPushButton("Guardar")
        save.clicked.connect(lambda: attempts.append("validate"))
        footer = save
        if kind == "container":
            footer = QWidget()
            layout = QHBoxLayout(footer)
            layout.addWidget(save)
    save.setAccessibleName("Guardar después de validar")
    save.setAutoDefault(False)
    save.setDefault(False)
    try:
        assert dialog.add_footer_widget(footer) is footer
        assert not save.isDefault()
        assert not save.autoDefault()
        dialog.show()
        settle(app)
        for profile in (density, "touch", "compact"):
            manager.set_density(profile)
            settle(app)
            assert dialog.available_geometry().contains(dialog.frameGeometry())
            assert not dialog.viewport.isAncestorOf(footer)
            assert dialog.rect().contains(QRect(footer.mapTo(dialog, QPoint()), footer.size()))
            assert save.height() >= density_metrics(profile).button_height
            assert save.accessibleName() == "Guardar después de validar"
            assert field.text() == "24"
        dialog.viewport.verticalScrollBar().setValue(dialog.viewport.verticalScrollBar().maximum())
        settle(app)
        assert not save.visibleRegion().isEmpty()
        QTest.mouseClick(save, Qt.LeftButton)
        assert attempts == ["validate"]
        assert dialog.isVisible()  # Validation still owns acceptance.
        if kind == "box":
            QTest.mouseClick(footer.button(QDialogButtonBox.Cancel), Qt.LeftButton)
            assert not dialog.isVisible()
    finally:
        sip.delete(dialog)
