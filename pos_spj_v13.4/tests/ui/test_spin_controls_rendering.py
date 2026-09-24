"""Numeric stepping remains visible and usable under the application QSS."""

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QRect, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QDoubleSpinBox, QLineEdit, QSpinBox, QStyle, QStyleOptionSpinBox, QVBoxLayout, QWidget

from frontend.desktop.components.integer_input import IntegerInput
from frontend.desktop.components.numeric_input import NumericInput
from frontend.desktop.themes.color_utils import AA_UI_COMPONENT, contrast_ratio
from frontend.desktop.themes.theme_manager import ThemeManager


def _button_rect(spin, subcontrol):
    option = QStyleOptionSpinBox()
    spin.initStyleOption(option)
    return spin.style().subControlRect(QStyle.CC_SpinBox, option, subcontrol, spin)


def _assert_arrow_visible(spin, subcontrol, background, minimum_contrast):
    button = _button_rect(spin, subcontrol)
    center = button.center()
    indicator = QRect(center.x() - 5, center.y() - 5, 11, 11)
    assert spin.rect().contains(button)
    assert button.contains(indicator), "El indicador debe caber dentro del botón de incremento."
    image = spin.grab().toImage()
    visible_pixels = sum(
        contrast_ratio(image.pixelColor(x, y).name(), background) >= minimum_contrast
        for x in range(indicator.left(), indicator.right() + 1)
        for y in range(indicator.top(), indicator.bottom() + 1)
    )
    assert visible_pixels >= 8, "El control numérico debe mostrar una flecha visible."
    row_widths = [sum(contrast_ratio(image.pixelColor(x, y).name(), background) >= minimum_contrast
                      for x in range(indicator.left(), indicator.right() + 1))
                  for y in range(indicator.top(), indicator.bottom() + 1)]
    row_widths = [width for width in row_widths if width]
    if subcontrol == QStyle.SC_SpinBoxUp:
        assert row_widths[0] < row_widths[-1], "La flecha debe apuntar hacia arriba."
    else:
        assert row_widths[0] > row_widths[-1], "La flecha debe apuntar hacia abajo."


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("density", ["compact", "comfortable", "touch"])
@pytest.mark.parametrize("factory", [QSpinBox, QDoubleSpinBox, IntegerInput, NumericInput])
def test_spin_arrows_render_and_step_without_changing_disabled_values(qt_font_resources, monkeypatch, theme, density, factory):
    app = qt_font_resources
    manager = ThemeManager()
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(app, theme, density=density)
    colors = manager.colors()
    host = QWidget()
    layout = QVBoxLayout(host)
    spin = factory()
    spin.setRange(0, 9)
    spin.setValue(4)
    other = QLineEdit()
    layout.addWidget(spin)
    layout.addWidget(other)
    host.resize(280, 180)
    try:
        host.show()
        other.setFocus(Qt.TabFocusReason)
        app.processEvents()
        assert not spin.styleSheet()
        editor = _button_rect(spin, QStyle.SC_SpinBoxEditField)
        assert spin.rect().contains(editor)
        for subcontrol in (QStyle.SC_SpinBoxUp, QStyle.SC_SpinBoxDown):
            assert not editor.intersects(_button_rect(spin, subcontrol))
        for subcontrol, expected in ((QStyle.SC_SpinBoxUp, 5), (QStyle.SC_SpinBoxDown, 4)):
            _assert_arrow_visible(spin, subcontrol, colors.SURFACE, AA_UI_COMPONENT)
            QTest.mouseClick(spin, Qt.LeftButton, pos=_button_rect(spin, subcontrol).center())
            app.processEvents()
            assert spin.value() == expected

        spin.setEnabled(False)
        app.processEvents()
        for subcontrol in (QStyle.SC_SpinBoxUp, QStyle.SC_SpinBoxDown):
            _assert_arrow_visible(spin, subcontrol, colors.DISABLED_BACKGROUND, 1.2)
            QTest.mouseClick(spin, Qt.LeftButton, pos=_button_rect(spin, subcontrol).center())
            assert spin.value() == 4

        spin.setEnabled(True)
        for value, unavailable in ((0, QStyle.SC_SpinBoxDown), (9, QStyle.SC_SpinBoxUp)):
            spin.setValue(value)
            other.setFocus(Qt.TabFocusReason)
            QTest.mouseMove(other)
            app.processEvents()
            _assert_arrow_visible(spin, unavailable, colors.SURFACE, 1.2)
            QTest.mouseClick(spin, Qt.LeftButton, pos=_button_rect(spin, unavailable).center())
            assert spin.value() == value

        spin.setValue(4)
        spin.setReadOnly(True)
        app.processEvents()
        for subcontrol in (QStyle.SC_SpinBoxUp, QStyle.SC_SpinBoxDown):
            QTest.mouseClick(spin, Qt.LeftButton, pos=_button_rect(spin, subcontrol).center())
            assert spin.value() == 4
    finally:
        host.close()
        sip.delete(host)
