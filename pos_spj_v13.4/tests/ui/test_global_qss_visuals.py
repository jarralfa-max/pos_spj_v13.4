"""Render canonical card and input states under the application's global QSS.

The gallery contains real components and neutral fixture text, with no database,
inline stylesheet, synthetic artwork, or alternative theme implementation.
Semantic pixel assertions verify the cascade; PNGs support human review without
claiming comparison against an approved visual baseline.
"""
import os
from pathlib import Path

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend.desktop.components.buttons import (
    DangerButton, GhostButton, IconButton, PrimaryButton, SecondaryButton,
)
from frontend.desktop.components.cards import (
    AlertCard, ChartCard, InfoCard, SectionCard, StandardCard, SummaryCard,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.components.integer_input import IntegerInput
from frontend.desktop.components.text_inputs import StandardLineEdit, StandardTextArea
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import (
    ResponsiveBreakpoints, Spacing, Typography, density_metrics,
)


STATES = (
    ("normal", "Normal"),
    ("readonly", "Solo lectura"),
    ("error", "Error"),
    ("disabled", "Deshabilitado"),
    ("readonly-disabled", "Lectura + deshab."),
    ("error-disabled", "Error + deshab."),
)


def _caption(text, parent=None, *, title=False):
    label = QLabel(text, parent)
    if title:
        font = label.font()
        font.setPointSize(Typography.SIZE_TITLE)
        font.setBold(True)
        label.setFont(font)
    return label


def _gallery(theme, density):
    window = QWidget()
    window.setWindowTitle("QSS global · componentes y estados")
    window.setFocusPolicy(Qt.StrongFocus)
    layout = QVBoxLayout(window)
    layout.setContentsMargins(Spacing.XL, Spacing.LG, Spacing.XL, Spacing.LG)
    layout.setSpacing(Spacing.SM)
    layout.addWidget(_caption("Componentes y estados · QSS global", title=True))
    mode = "Claro" if theme == "light" else "Oscuro"
    profile = "Cómoda" if density == "comfortable" else "Táctil"
    subtitle = _caption(f"Tema: {mode}   ·   Densidad: {profile}   ·   Datos de demostración")
    subtitle.setProperty("role", "subtitle")
    layout.addWidget(subtitle)

    card_specs = (
        (StandardCard(), "Estándar", "Superficie base", "SURFACE", "BORDER_DEFAULT"),
        (SectionCard(title="Sección"), None, "Contenido agrupado", "SURFACE", "BORDER_DEFAULT"),
        (SummaryCard(), "Resumen", "Superficie elevada", "SURFACE_ELEVATED", "BORDER_DEFAULT"),
        (InfoCard(), "Información", "Mensaje informativo", "INFO_SUBTLE", "INFO_BORDER"),
        (AlertCard(), "Advertencia", "Requiere atención", "WARNING_SUBTLE", "WARNING_BORDER"),
        (AlertCard(variant="danger"), "Peligro", "Acción sensible", "DANGER_SUBTLE", "DANGER_BORDER"),
        (ChartCard(), "Gráfica", "Contenedor visual", "SURFACE", "BORDER_DEFAULT"),
    )
    cards = QHBoxLayout()
    cards.setSpacing(Spacing.SM)
    for card, heading, description, _surface, _border in card_specs:
        if heading:
            card.add(_caption(heading))
        card.add(_caption(description))
        card.body().addStretch()
        card.setMinimumHeight(100)
        cards.addWidget(card, 1)
    layout.addLayout(cards)

    layout.addWidget(_caption("Captura y validación"))
    fields = QGridLayout()
    fields.setHorizontalSpacing(Spacing.SM)
    fields.setVerticalSpacing(Spacing.SM)
    fields.addWidget(_caption("Componente"), 0, 0)
    for column, (_state, title) in enumerate(STATES, start=1):
        fields.addWidget(_caption(title), 0, column)
        fields.setColumnStretch(column, 1)

    controls = []
    for row, (kind, title) in enumerate((
        ("line", "Texto"), ("integer", "Entero"),
        ("combo", "Selección"), ("area", "Texto multilínea"),
    ), start=1):
        fields.addWidget(_caption(title), row, 0)
        for column, (state, _title) in enumerate(STATES, start=1):
            # A native combo has no readOnly contract. Do not imply that merely
            # marking its editable text readonly also freezes its selection.
            if kind == "combo" and "readonly" in state:
                note = _caption("No aplica")
                note.setProperty("role", "muted")
                fields.addWidget(note, row, column)
                continue
            if kind == "line":
                field = StandardLineEdit(keyboard_enabled=False)
                field.setText("Texto")
            elif kind == "integer":
                field = IntegerInput()
            elif kind == "combo":
                field = QComboBox()
                field.addItems(("Opción", "Alternativa"))
            else:
                field = StandardTextArea()
                field.setPlainText("Nota")
                field.setFixedHeight(density_metrics().input_height + Spacing.XL)
            if "readonly" in state:
                field.setReadOnly(True)
            if "error" in state:
                field.setProperty("state", "error")
            if "disabled" in state:
                field.setEnabled(False)
            field.setAccessibleName(f"{title}: {_title}")
            fields.addWidget(field, row, column)
            controls.append((field, kind, state))
    layout.addLayout(fields)

    layout.addWidget(_caption("Acciones"))
    actions = QHBoxLayout()
    actions.setSpacing(Spacing.SM)
    buttons = (
        PrimaryButton("Guardar"), SecondaryButton("Cancelar"),
        GhostButton("Ver detalles"), DangerButton("Eliminar"),
        IconButton(Icons.SEARCH, "Buscar"), PrimaryButton("No disponible"),
    )
    buttons[-1].setEnabled(False)
    for button in buttons:
        actions.addWidget(button)
    actions.addStretch()
    layout.addLayout(actions)
    note = _caption("Las selecciones no tienen modo de solo lectura. Los campos numéricos comienzan en cero.")
    note.setProperty("role", "muted")
    layout.addWidget(note)
    layout.addStretch()
    return window, card_specs, controls, buttons


def _pixel(widget, x, y):
    return widget.grab().toImage().pixelColor(x, y).name().upper()


@pytest.mark.parametrize("size", ResponsiveBreakpoints.VALIDATION_SIZES)
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("density", ["comfortable", "touch"])
def test_global_qss_states_are_visible(qt_font_resources, ui_tmp_path, monkeypatch, size, theme, density):
    app = qt_font_resources
    assert QFontDatabase().families(), "Visual evidence requires installed fonts"
    manager = ThemeManager()
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(app, theme, density=density)
    window, cards, fields, buttons = _gallery(theme, density)
    try:
        window.show()
        window.resize(*size)
        window.setFocus(Qt.OtherFocusReason)
        for _ in range(4):
            app.processEvents()
        assert (window.width(), window.height()) == size
        colors = manager.colors()
        for card, _heading, _description, surface, border in cards:
            assert _pixel(card, card.width() // 2, card.height() - Spacing.SM) == getattr(colors, surface)
            assert _pixel(card, 0, card.height() // 2) == getattr(colors, border)
        for field, kind, state in fields:
            assert field.height() >= density_metrics().input_height
            if "disabled" in state:
                assert _pixel(field, 0, field.height() // 2) == colors.DISABLED_BORDER
            elif "error" in state:
                assert _pixel(field, 0, field.height() // 2) == colors.DANGER_DEFAULT
            elif kind == "line" and state == "readonly":
                assert _pixel(field, field.width() // 2, field.height() // 2) == colors.SURFACE_MUTED
        for widget in [*(card[0] for card in cards), *(field[0] for field in fields), *buttons]:
            assert not widget.styleSheet(), widget.accessibleName()
            assert widget.isVisible()
            assert window.rect().contains(QRect(widget.mapTo(window, QPoint()), widget.size())), widget.accessibleName()
            assert widget.visibleRegion().boundingRect() == widget.rect(), widget.accessibleName()
        artifacts = Path(os.environ.get("SPJ_UI_VISUAL_ARTIFACTS", str(ui_tmp_path)))
        artifacts.mkdir(parents=True, exist_ok=True)
        image = window.grab()
        assert not image.isNull()
        assert image.save(str(artifacts / f"qss-states-{theme}-{density}-{size[0]}x{size[1]}.png"))
    finally:
        window.close()
        sip.delete(window)
