"""Protect contrast where Qt actually applies semantic QSS to controls."""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import QLineEdit, QVBoxLayout, QWidget
import pytest

from frontend.desktop.components.buttons import PrimaryButton
from frontend.desktop.components.form_field import FormField
from frontend.desktop.themes.color_utils import AA_NORMAL_TEXT, AA_UI_COMPONENT, contrast_ratio
from frontend.desktop.themes.theme_manager import ThemeManager


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_small_form_helper_keeps_normal_text_contrast(qt_font_resources, theme):
    app = qt_font_resources
    ThemeManager().apply(app, theme)
    field = FormField("Referencia", QLineEdit(), helper="Captura una referencia")
    try:
        field.show()
        app.processEvents()
        label = field._helper
        assert label.font().pixelSize() == 11
        foreground = label.palette().color(QPalette.WindowText).name()
        background = field.palette().color(QPalette.Window).name()
        assert contrast_ratio(foreground, background) >= AA_NORMAL_TEXT
    finally:
        field.close()
        field.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_rendered_input_border_identifies_the_field(qt_font_resources, theme):
    app = qt_font_resources
    ThemeManager().apply(app, theme)
    host = QWidget()
    layout = QVBoxLayout(host)
    field = QLineEdit()
    other = QLineEdit()
    layout.addWidget(field)
    layout.addWidget(other)
    try:
        host.show()
        other.setFocus(Qt.TabFocusReason)
        app.processEvents()
        assert not field.hasFocus()
        image = field.grab().toImage()
        border = image.pixelColor(0, image.height() // 2).name()
        inside = image.pixelColor(image.width() // 2, image.height() // 2).name()
        outside = host.palette().color(QPalette.Window).name()
        assert contrast_ratio(border, inside) >= AA_UI_COMPONENT
        assert contrast_ratio(border, outside) >= AA_UI_COMPONENT
    finally:
        host.close()
        host.deleteLater()
        app.processEvents()


def test_light_primary_focus_changes_the_visible_border(qt_font_resources):
    app = qt_font_resources
    ThemeManager().apply(app, "light")
    host = QWidget()
    layout = QVBoxLayout(host)
    button = PrimaryButton("Guardar")
    other = QLineEdit()
    layout.addWidget(button)
    layout.addWidget(other)
    try:
        host.show()
        other.setFocus(Qt.TabFocusReason)
        app.processEvents()
        assert not button.hasFocus()
        before = button.grab().toImage()
        button.setFocus(Qt.TabFocusReason)
        app.processEvents()
        assert button.hasFocus()
        after = button.grab().toImage()
        assert before.size() == after.size()
        x = after.width() // 2
        focused_border = after.pixelColor(x, 0).name()
        previous_border = before.pixelColor(x, 0).name()
        filled_interior = after.pixelColor(x, 4).name()
        host_background = host.palette().color(QPalette.Window).name()
        assert contrast_ratio(focused_border, previous_border) >= AA_UI_COMPONENT
        assert contrast_ratio(focused_border, filled_interior) >= AA_UI_COMPONENT
        assert contrast_ratio(focused_border, host_background) >= AA_UI_COMPONENT
    finally:
        host.close()
        host.deleteLater()
        app.processEvents()
