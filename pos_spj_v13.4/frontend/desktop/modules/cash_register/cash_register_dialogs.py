"""Standard CASH-23 dialogs for cash register workflows.

These dialogs capture UI data only. Authorization, limits, audit and workflow
effects remain in application services/use cases.
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt5.QtWidgets import QLabel, QDialogButtonBox

from frontend.desktop.components.dialogs import FormDialog, StandardDialog
from frontend.desktop.components.money_input import MoneyInput
from frontend.desktop.components.text_inputs import PasswordInput, StandardLineEdit, StandardTextArea
from frontend.desktop.components.tooltip import apply_tooltip
from frontend.desktop.themes.tokens import DialogMetrics


@dataclass(frozen=True)
class CashReasonResult:
    amount: float
    reason: str
    notes: str


@dataclass(frozen=True)
class HotAuthorizationResult:
    authorizer_user: str
    password: str
    reason: str


class CashReasonDialog(FormDialog):
    """Capture amount, reason and notes for movements, refunds or disputes."""

    def __init__(self, parent=None, *, title: str = "Motivo de caja") -> None:
        super().__init__(parent, title=title, width=DialogMetrics.WIDTH_MD)
        self.amount = MoneyInput(self)
        self.reason = StandardLineEdit(
            self,
            placeholder="Ej. retiro a tesoreria, ajuste autorizado",
            max_length=120,
            required=True,
        )
        self.notes = StandardTextArea(
            self,
            placeholder="Notas operativas visibles para auditoria",
            max_length=500,
        )
        apply_tooltip(self.amount, "Captura el importe exacto de la operacion.")
        apply_tooltip(self.reason, "Motivo corto requerido para auditoria.")
        apply_tooltip(self.notes, "Contexto adicional; evita datos sensibles innecesarios.")
        self.form.addRow("Importe", self.amount)
        self.form.addRow("Motivo", self.reason)
        self.form.addRow("Notas", self.notes)
        self._buttons = self.add_button_box(ok_text="Continuar", cancel_text="Cancelar")

    def _validate(self) -> bool:
        ok = bool(self.reason.value())
        self.reason.setProperty("state", "" if ok else "error")
        self.reason.style().unpolish(self.reason)
        self.reason.style().polish(self.reason)
        if not ok:
            self.reason.setFocus()
        return ok

    def accept(self) -> None:
        if self._validate():
            super().accept()

    def result_value(self) -> CashReasonResult:
        return CashReasonResult(
            amount=float(self.amount.value()),
            reason=self.reason.value(),
            notes=self.notes.value(),
        )


class HotAuthorizationDialog(FormDialog):
    """Capture supervisor credentials for hot authorization."""

    def __init__(self, parent=None, *, title: str = "Autorizacion en caliente") -> None:
        super().__init__(parent, title=title, width=DialogMetrics.WIDTH_SM)
        self.authorizer = StandardLineEdit(
            self,
            placeholder="Usuario supervisor",
            max_length=80,
            required=True,
        )
        self.password = PasswordInput(self, placeholder="Contrasena")
        self.reason = StandardTextArea(
            self,
            placeholder="Motivo de la autorizacion",
            max_length=300,
        )
        apply_tooltip(self.authorizer, "Usuario con permiso para autorizar esta accion.")
        apply_tooltip(self.password, "La clave no se registra en auditoria.")
        apply_tooltip(self.reason, "Motivo visible para revision posterior.")
        self.form.addRow("Autoriza", self.authorizer)
        self.form.addRow("Clave", self.password)
        self.form.addRow("Motivo", self.reason)
        self.add_button_box(ok_text="Autorizar", cancel_text="Cancelar")

    def result_value(self) -> HotAuthorizationResult:
        return HotAuthorizationResult(
            authorizer_user=self.authorizer.value(),
            password=self.password.value(),
            reason=self.reason.value(),
        )


class CashPrintPreviewDialog(StandardDialog):
    """Small themed dialog used before sending X/Z cut documents to a printer."""

    def __init__(self, parent=None, *, title: str, summary: str) -> None:
        super().__init__(parent, title=title, width=DialogMetrics.WIDTH_MD)
        label = QLabel(summary, self)
        label.setWordWrap(True)
        label.setProperty("role", "muted")
        self.content_layout().addWidget(label)
        self.add_button_box(ok_text="Imprimir", cancel_text="Cerrar")
