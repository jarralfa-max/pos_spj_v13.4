"""Modal prompt helpers preserve text/choice results and cancellation semantics."""
import pytest
from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QComboBox, QDialogButtonBox, QLineEdit

from frontend.desktop.components.dialogs import FormDialog
from tests.ui.test_standard_window_geometry import settle


@pytest.mark.parametrize("kind", ["text", "choice", "editable_choice"])
@pytest.mark.parametrize("accepted", [False, True])
def test_prompt_keeps_capture_and_modal_result(qt_font_resources, monkeypatch, kind, accepted):
    app = qt_font_resources
    observed = []

    def interact(dialog):
        monkeypatch.setattr(dialog, "available_geometry", lambda: QRect(0, 0, 640, 480))
        dialog.show()
        settle(app)
        assert dialog.windowTitle() == "Captura"
        assert not dialog.windowIcon().isNull()
        assert dialog.available_geometry().contains(dialog.frameGeometry())
        box = dialog.findChild(QDialogButtonBox)
        assert not dialog.viewport.isAncestorOf(box)
        for button in box.buttons():
            assert dialog.rect().contains(QRect(button.mapTo(dialog, QPoint()), button.size()))
        if kind == "text":
            field = dialog.findChild(QLineEdit)
            assert field.text() == "Anterior"
            field.setText("  Captura nueva  ")
            expected = "  Captura nueva  "
        else:
            field = dialog.findChild(QComboBox)
            assert field.currentText() == "Tienda"
            assert field.isEditable() == (kind == "editable_choice")
            if kind == "editable_choice":
                field.setEditText("Otro canal")
                expected = "Otro canal"
            else:
                field.setCurrentIndex(0)
                expected = "Mostrador"
        assert field.accessibleName() == "Dato:"
        field.setFocus()
        QTest.keyClick(dialog, Qt.Key_Return if accepted else Qt.Key_Escape)
        observed.append((expected, dialog.result()))
        return dialog.result()

    monkeypatch.setattr(FormDialog, "exec_", interact)
    if kind == "text":
        result = FormDialog.get_text(None, "Captura", "Dato:", text="Anterior")
    else:
        result = FormDialog.get_item(None, "Captura", "Dato:", ["Mostrador", "Tienda"],
                                     1, kind == "editable_choice")
    assert len(observed) == 1
    assert result == (observed[0][0] if accepted else "", accepted)


def test_text_prompt_leaves_empty_value_validation_to_caller(qt_font_resources, monkeypatch):
    def accept_empty(dialog):
        assert dialog.findChild(QLineEdit).text() == ""
        dialog.accept()
        return dialog.result()

    monkeypatch.setattr(FormDialog, "exec_", accept_empty)
    assert FormDialog.get_text(None, "Motivo", "Motivo:") == ("", True)
