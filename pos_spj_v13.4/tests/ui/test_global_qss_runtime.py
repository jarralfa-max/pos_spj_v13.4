"""Verify the global cascade on rendered widgets, not stylesheet substrings."""
from functools import partial

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import QComboBox, QLineEdit, QPlainTextEdit, QSpinBox, QVBoxLayout, QWidget

from frontend.desktop.components.cards import AlertCard, ChartCard, InfoCard, SectionCard, StandardCard, SummaryCard
from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.themes.qss_builder import build_qss
from frontend.desktop.themes.theme_manager import ThemeManager


@pytest.fixture
def manager(qt_font_resources, monkeypatch):
    manager = ThemeManager()
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(qt_font_resources, "light", density="comfortable")
    yield manager
    qt_font_resources.sendPostedEvents(None, QEvent.DeferredDelete)


def sample(widget, x, y):
    return widget.grab().toImage().pixelColor(x, y).name().upper()


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("factory,surface,border", [
    (StandardCard, "SURFACE", "BORDER_DEFAULT"),
    (SectionCard, "SURFACE", "BORDER_DEFAULT"),
    (SummaryCard, "SURFACE_ELEVATED", "BORDER_DEFAULT"),
    (InfoCard, "INFO_SUBTLE", "INFO_BORDER"),
    (AlertCard, "WARNING_SUBTLE", "WARNING_BORDER"),
    (partial(AlertCard, variant="danger"), "DANGER_SUBTLE", "DANGER_BORDER"),
    (ChartCard, "SURFACE", "BORDER_DEFAULT"),
])
def test_canonical_card_variants_keep_their_semantic_surface(manager, qt_font_resources, theme, factory, surface, border):
    manager.apply(qt_font_resources, theme)
    card = factory()
    try:
        card.resize(240, 100)
        card.show()
        qt_font_resources.processEvents()
        assert sample(card, 120, 50) == getattr(manager.colors(), surface)
        assert sample(card, 0, 50) == getattr(manager.colors(), border)
        assert not card.styleSheet()
    finally:
        card.close()
        sip.delete(card)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("name", ["standardLineEdit", "filePathField"])
def test_disabled_readonly_fields_use_disabled_colors(manager, qt_font_resources, theme, name):
    manager.apply(qt_font_resources, theme)
    field = QLineEdit()
    try:
        field.setObjectName(name)
        field.setReadOnly(True)
        field.setEnabled(False)
        field.resize(240, 48)
        field.show()
        qt_font_resources.processEvents()
        assert sample(field, 120, 24) == manager.colors().DISABLED_BACKGROUND
        assert field.palette().color(QPalette.Disabled, QPalette.Text).name().upper() == manager.colors().TEXT_DISABLED
        field.setEnabled(True)
        qt_font_resources.processEvents()
        assert sample(field, 120, 24) == manager.colors().SURFACE_MUTED
    finally:
        field.close()
        sip.delete(field)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("control", [QLineEdit, QComboBox, QSpinBox, QPlainTextEdit])
def test_error_field_reverts_to_disabled_border_then_restores_error(manager, qt_font_resources, theme, control):
    manager.apply(qt_font_resources, theme)
    host = QWidget()
    layout = QVBoxLayout(host)
    field = control()
    field.setProperty("state", "error")
    other = QLineEdit()
    layout.addWidget(field)
    layout.addWidget(other)
    try:
        host.show()
        other.setFocus(Qt.TabFocusReason)
        qt_font_resources.processEvents()
        assert sample(field, 0, field.height() // 2) == manager.colors().DANGER_DEFAULT
        field.setEnabled(False)
        qt_font_resources.processEvents()
        assert sample(field, 0, field.height() // 2) == manager.colors().DISABLED_BORDER
        field.setEnabled(True)
        other.setFocus(Qt.TabFocusReason)
        qt_font_resources.processEvents()
        assert field.property("state") == "error"
        assert sample(field, 0, field.height() // 2) == manager.colors().DANGER_DEFAULT
    finally:
        host.close()
        sip.delete(host)


@pytest.mark.parametrize("operation,expected_theme,expected_density", [
    (lambda manager: manager.set_theme("dark"), "dark", "comfortable"),
    (lambda manager: manager.toggle(), "dark", "comfortable"),
    (lambda manager: manager.set_density("touch"), "light", "touch"),
])
def test_implicit_application_is_updated_before_observers(manager, qt_font_resources, operation, expected_theme, expected_density):
    app = qt_font_resources
    field = StandardLineEdit(keyboard_enabled=False)
    field.setText("Dato en captura")
    observed = []

    def observe(_value):
        observed.append((app.property("spjTheme"), app.property("spjDensity"), app.styleSheet()))

    manager.theme_changed.connect(observe)
    manager.density_changed.connect(observe)
    try:
        field.show()
        operation(manager)
        app.processEvents()
        expected = (expected_theme, expected_density, build_qss(expected_theme, density=expected_density))
        assert observed == [expected]
        assert field.palette().color(QPalette.Base).name().upper() == manager.colors().SURFACE
        assert field.text() == "Dato en captura"
        assert field.styleSheet() == ""
    finally:
        field.close()
        sip.delete(field)
