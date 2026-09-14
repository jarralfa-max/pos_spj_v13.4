"""Keep the native dropdown affordance visible under the central stylesheet."""

import pytest
from PyQt5.QtCore import QRect, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QLineEdit, QStyle, QStyleOptionComboBox, QVBoxLayout, QWidget

from frontend.desktop.components.selection_controls import StandardComboBox
from frontend.desktop.themes.color_utils import AA_UI_COMPONENT, contrast_ratio
from frontend.desktop.themes.theme_manager import ThemeManager


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("density", ["compact", "comfortable", "touch"])
def test_combo_arrow_remains_visible_and_opens_options(qt_font_resources, monkeypatch, theme, density):
    app = qt_font_resources
    manager = ThemeManager()
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(app, theme, density=density)
    host = QWidget()
    layout = QVBoxLayout(host)
    combo = StandardComboBox(accessible_name="Tema de esta terminal")
    combo.addItems(["Claro", "Oscuro"])
    other = QLineEdit()
    layout.addWidget(combo)
    layout.addWidget(other)
    host.resize(260, 160)
    try:
        host.show()
        other.setFocus(Qt.TabFocusReason)
        app.processEvents()
        option = QStyleOptionComboBox()
        combo.initStyleOption(option)
        arrow = combo.style().subControlRect(QStyle.CC_ComboBox, option, QStyle.SC_ComboBoxArrow, combo)
        center = arrow.center()
        indicator = QRect(center.x() - 5, center.y() - 5, 11, 11)
        assert combo.rect().contains(indicator)
        image = combo.grab().toImage()
        background = manager.colors().SURFACE
        visible_pixels = sum(
            contrast_ratio(image.pixelColor(x, y).name(), background) >= AA_UI_COMPONENT
            for x in range(indicator.left(), indicator.right() + 1)
            for y in range(indicator.top(), indicator.bottom() + 1)
        )
        assert visible_pixels >= 8, "El desplegable debe mostrar una flecha con contraste visible."
        QTest.mouseClick(combo, Qt.LeftButton, pos=center)
        app.processEvents()
        assert combo.view().isVisible()
        QTest.keyClick(combo.view(), Qt.Key_Down)
        QTest.keyClick(combo.view(), Qt.Key_Return)
        app.processEvents()
        assert combo.currentText() == "Oscuro"
        assert not combo.view().isVisible()
    finally:
        host.close()
        host.deleteLater()
        app.processEvents()
