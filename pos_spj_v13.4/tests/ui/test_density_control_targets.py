"""Measured target areas and focus geometry for the three desktop profiles."""
import pytest
from PyQt5 import sip
from PyQt5.QtCore import QPoint, Qt, QSettings
from PyQt5.QtTest import QSignalSpy, QTest
from PyQt5.QtWidgets import QLineEdit, QVBoxLayout, QWidget

from frontend.desktop.components.selection_controls import StandardCheckBox, StandardRadioButton, StandardComboBox
from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.components.buttons import PrimaryButton, GhostButton, IconButton
from frontend.desktop.components.icons import Icons
from frontend.desktop.components.tabs import Tabs
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import density_metrics


@pytest.fixture
def manager(qt_font_resources, ui_tmp_path, monkeypatch):
    manager = ThemeManager(QSettings(str(ui_tmp_path / "targets.ini"), QSettings.IniFormat))
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    return manager


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("density", ["compact", "comfortable", "touch"])
@pytest.mark.parametrize("factory", [StandardCheckBox, StandardRadioButton])
def test_boolean_focus_does_not_resize_target(manager, qt_font_resources, theme, density, factory):
    app = qt_font_resources
    manager.apply(app, theme, density=density)
    host = QWidget()
    layout = QVBoxLayout(host)
    control, other = factory("Activar opción"), QLineEdit()
    layout.addWidget(control)
    layout.addWidget(other)
    layout.addStretch()
    try:
        host.show()
        for target in (other, control, other):
            target.setFocus(Qt.TabFocusReason)
            app.processEvents()
            assert control.height() == density_metrics(density).input_height
    finally:
        sip.delete(host)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("density", ["compact", "comfortable", "touch"])
def test_checkbox_whole_target_accepts_clicks(manager, qt_font_resources, theme, density):
    app = qt_font_resources
    manager.apply(app, theme, density=density)
    control = StandardCheckBox("Activar opción")
    control.resize(240, density_metrics(density).input_height)
    try:
        control.show()
        app.processEvents()
        clicked = QSignalSpy(control.clicked)
        for y in (2, control.height() - 3):
            previous = len(clicked)
            QTest.mouseClick(control, Qt.LeftButton, pos=QPoint(control.width() // 2, y))
            assert len(clicked) == previous + 1, "La altura visible debe ser también el área clicable."
        control.setEnabled(False)
        QTest.mouseClick(control, Qt.LeftButton, pos=control.rect().center())
        assert len(clicked) == 2
    finally:
        sip.delete(control)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("density", ["compact", "comfortable", "touch"])
def test_tab_selection_keeps_profile_height(manager, qt_font_resources, theme, density):
    app = qt_font_resources
    manager.apply(app, theme, density=density)
    tabs = Tabs()
    for label in ("Resumen", "Movimientos"):
        tabs.addTab(QWidget(), label)
    try:
        tabs.resize(500, 240)
        tabs.show()
        for index in (0, 1, 0):
            tabs.setCurrentIndex(index)
            app.processEvents()
            assert all(tabs.tabBar().tabRect(i).height() == density_metrics(density).tab_height
                       for i in range(tabs.count()))
    finally:
        sip.delete(tabs)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("density", ["compact", "comfortable", "touch"])
def test_input_focus_keeps_geometry(manager, qt_font_resources, theme, density):
    app = qt_font_resources
    manager.apply(app, theme, density=density)
    host = QWidget()
    layout = QVBoxLayout(host)
    control, other = StandardLineEdit(keyboard_enabled=False), StandardComboBox()
    control.setText("Referencia en captura")
    other.addItems(["Pendiente", "Confirmado"])
    layout.addWidget(control)
    layout.addWidget(other)
    layout.addStretch()
    try:
        host.show()
        host.activateWindow()
        heights = []
        for target in (other, control, other):
            target.setFocus(Qt.TabFocusReason)
            for _ in range(4):
                app.processEvents()
            assert target.hasFocus()
            heights.append((control.height(), other.height()))
            assert control.text() == "Referencia en captura"
        assert len(set(heights)) == 1, "El foco debe conservar la altura de ambos campos."
    finally:
        sip.delete(host)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_combo_popup_rows_follow_live_density(manager, qt_font_resources, theme):
    app = qt_font_resources
    manager.apply(app, theme, density="compact")
    combo = StandardComboBox()
    combo.addItems(["Compacta", "Cómoda", "Táctil"])
    combo.setCurrentIndex(1)
    try:
        combo.show()
        for density in ("compact", "comfortable", "touch", "compact"):
            manager.set_density(density)
            combo.showPopup()
            for _ in range(4):
                app.processEvents()
            view = combo.view()
            assert all(view.visualRect(combo.model().index(i, 0)).height() >= density_metrics(density).input_height
                       for i in range(combo.count()))
            assert combo.currentIndex() == 1
            combo.hidePopup()
    finally:
        sip.delete(combo)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("density", ["compact", "comfortable", "touch"])
@pytest.mark.parametrize("kind", ["primary", "ghost", "icon", "checkbox", "radio"])
def test_reapplying_style_while_focused_keeps_target_size(manager, qt_font_resources, theme, density, kind):
    app = qt_font_resources
    manager.apply(app, theme, density=density)
    host = QWidget()
    layout = QVBoxLayout(host)
    factories = dict(primary=PrimaryButton, ghost=GhostButton,
                     checkbox=StandardCheckBox, radio=StandardRadioButton)
    control = IconButton(Icons.SEARCH, "Buscar") if kind == "icon" else factories[kind]("Consultar")
    other = StandardLineEdit(keyboard_enabled=False)
    layout.addWidget(control, 0, Qt.AlignLeft)
    layout.addWidget(other)
    layout.addStretch()
    host.resize(500, 450)
    metrics = density_metrics(density)
    expected = metrics.icon_button_size if kind == "icon" else metrics.button_height
    try:
        host.show()
        host.activateWindow()
        for target in (other, control, other):
            target.setFocus(Qt.TabFocusReason)
            for _ in range(4):
                app.processEvents()
            assert target.hasFocus()
            manager.apply(app, theme, density=density)
            for _ in range(4):
                app.processEvents()
            assert control.height() == expected
            if kind == "icon":
                assert control.width() == expected
    finally:
        sip.delete(host)
