"""Render canonical dialogs on five simulated desktops with real Qt text metrics.

Set SPJ_DIALOG_VISUAL_ARTIFACTS to retain the thirty theme/density captures.
These tests simulate available monitor areas; they do not emulate physical DPI.
"""
import os
from pathlib import Path

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QPoint, QRect, QSettings
from PyQt5.QtWidgets import QApplication, QDialogButtonBox, QFormLayout, QLabel

from frontend.desktop.components.dialogs import (
    ConfirmationDialog,
    DestructiveConfirmationDialog,
    StandardDialog,
)
from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import ResponsiveBreakpoints, density_metrics
from tests.ui.test_standard_window_geometry import DesktopScreen, settle


def _appearance(app, ui_tmp_path, monkeypatch, theme, density):
    manager = ThemeManager(QSettings(str(ui_tmp_path / "dialogs.ini"), QSettings.IniFormat))
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(app, theme, density=density)
    return manager


def _desktop(monkeypatch, size):
    screen = DesktopScreen(QRect(80, 40, *size))
    monkeypatch.setattr(StandardDialog, "screen", lambda self: screen)
    monkeypatch.setattr(QApplication, "primaryScreen", lambda: screen)
    monkeypatch.setattr(QApplication, "screens", lambda: [screen])
    return screen


def _rect_in(widget, ancestor):
    return QRect(widget.mapTo(ancestor, QPoint()), widget.size())


def _assert_footer_accessible(dialog, box):
    assert not dialog.viewport.isAncestorOf(box)
    assert dialog.rect().contains(_rect_in(box, dialog))
    assert _rect_in(box, dialog).top() >= _rect_in(dialog.viewport, dialog).bottom()
    for button in box.buttons():
        assert button.isVisible()
        assert not button.visibleRegion().isEmpty()
        assert dialog.rect().contains(_rect_in(button, dialog))
        assert button.height() >= density_metrics().button_height


@pytest.mark.parametrize("size", ResponsiveBreakpoints.VALIDATION_SIZES)
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("density", ["compact", "comfortable", "touch"])
def test_long_form_keeps_footer_and_last_field_accessible(
    qt_font_resources, ui_tmp_path, monkeypatch, size, theme, density,
):
    app = qt_font_resources
    manager = _appearance(app, ui_tmp_path, monkeypatch, theme, density)
    screen = _desktop(monkeypatch, size)
    dialog = StandardDialog(title="Captura de información · JUANIS", width=760)
    form = QFormLayout()
    fields = []
    for index in range(32):
        field = StandardLineEdit(keyboard_enabled=False)
        field.setAccessibleName(f"Dato {index + 1}")
        form.addRow(f"Dato {index + 1}", field)
        fields.append(field)
    dialog.content_layout().addLayout(form)
    box = dialog.add_button_box(ok_text="Guardar", cancel_text="Cancelar")
    fields[0].setText("Captura pendiente")
    fields[-1].setText("Último dato conservado")
    try:
        dialog.show()
        settle(app)
        assert screen.availableGeometry().contains(dialog.frameGeometry())
        assert dialog.styleSheet() == "" and not dialog.windowIcon().isNull()
        assert dialog.viewport.verticalScrollBar().maximum() > 0
        _assert_footer_accessible(dialog, box)

        # Resize the live controls through another density, preserving the form.
        alternate = "comfortable" if density == "touch" else "touch"
        for profile in (alternate, density):
            manager.apply(app, theme, density=profile)
            settle(app)
            assert screen.availableGeometry().contains(dialog.frameGeometry())
            assert fields[0].text() == "Captura pendiente"
            assert fields[-1].text() == "Último dato conservado"
            assert fields[0].height() >= density_metrics().input_height
            _assert_footer_accessible(dialog, box)

        dialog.viewport.ensureWidgetVisible(fields[-1])
        settle(app)
        assert dialog.viewport.viewport().rect().contains(
            _rect_in(fields[-1], dialog.viewport.viewport())
        )
        assert dialog.viewport.verticalScrollBar().value() > 0
        _assert_footer_accessible(dialog, box)
        dialog.viewport.verticalScrollBar().setValue(0)
        settle(app)
        artifact_path = os.environ.get("SPJ_DIALOG_VISUAL_ARTIFACTS")
        if artifact_path:
            directory = Path(artifact_path)
            directory.mkdir(parents=True, exist_ok=True)
            assert dialog.grab().save(str(
                directory / f"{theme}-{density}-{size[0]}x{size[1]}-dialog.png"
            ))
    finally:
        sip.delete(dialog)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("dialog_type", [ConfirmationDialog, DestructiveConfirmationDialog])
def test_confirmation_titles_wrap_and_actions_remain_visible(
    qt_font_resources, ui_tmp_path, monkeypatch, theme, dialog_type,
):
    app = qt_font_resources
    _appearance(app, ui_tmp_path, monkeypatch, theme, "touch")
    screen = _desktop(monkeypatch, (1280, 720))
    title = "Confirmar los cambios pendientes antes de continuar con esta operación"
    dialog = dialog_type(
        title=title,
        message="Revisa la información capturada. Puedes cancelar para volver al formulario.",
    )
    try:
        dialog.show()
        settle(app)
        assert screen.availableGeometry().contains(dialog.frameGeometry())
        heading = next(label for label in dialog.findChildren(QLabel)
                       if label.property("role") == "dialogTitle")
        assert heading.text() == dialog.windowTitle() == title
        assert heading.wordWrap()
        assert heading.height() >= heading.heightForWidth(heading.width())
        assert dialog.rect().contains(_rect_in(heading, dialog))
        box = dialog.findChild(QDialogButtonBox)
        _assert_footer_accessible(dialog, box)
        if dialog_type is DestructiveConfirmationDialog:
            assert box.button(QDialogButtonBox.Ok).property("variant") == "danger"
            assert box.button(QDialogButtonBox.Cancel).isDefault()
            assert not box.button(QDialogButtonBox.Ok).isDefault()
    finally:
        sip.delete(dialog)
