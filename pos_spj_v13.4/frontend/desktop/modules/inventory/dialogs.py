"""Inventory action dialogs (P0-B pilot — Cuarentena).

Presentation-only: captures the reason text the DisposeQuarantineUseCase
audits. No business logic, no backend calls — the page reads the captured
value and hands it to the presenter after the dialog is accepted.
"""

from __future__ import annotations

from frontend.desktop.components.dialogs import FormDialog
from frontend.desktop.components.text_inputs import StandardTextArea


class DisposeQuarantineDialog(FormDialog):
    """Motivo de disposición (baja definitiva) de una cuarentena — auditado."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Disponer cuarentena")
        self.reason_input = StandardTextArea(self, placeholder="Motivo de la disposición…")
        self.reason_input.setMaximumHeight(90)
        self.form.addRow("Motivo:", self.reason_input)
        self.add_button_box(ok_text="Disponer")

    def reason(self) -> str:
        return self.reason_input.value()
