"""CancelSaleDialog — confirmar la cancelación de la venta en curso, con motivo
(§42: "requerir motivo"; §63: auditar cancelación).

Re-auditoría POS (2026-10-01): F8 (o el botón) cancelaba la venta ENTERA al
instante, sin confirmar y con el motivo fijo "Cancelada por cajero". Un dedo en
la tecla equivocada tiraba la venta. Ahora se confirma y el motivo lo escribe
quien cancela; el caso de uso lo guarda en el evento de cancelación.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QDialogButtonBox, QLabel

from frontend.desktop.components import FormField, StandardDialog, StandardForm, StandardLineEdit


class CancelSaleDialog(StandardDialog):
    def __init__(self, *, line_count: int, total_text: str, parent=None) -> None:
        super().__init__(parent, title="Cancelar venta")
        self.setObjectName("posCancelDialog")
        self.reason: str | None = None

        message = QLabel(
            f"Se cancelará la venta en curso ({line_count} línea(s), {total_text}). "
            "La mercancía apartada vuelve a estar disponible.", self)
        message.setWordWrap(True)
        self.content_layout().addWidget(message)

        form = StandardForm(self)
        self._reason = StandardLineEdit(self, placeholder="Por qué se cancela")
        form.add_field("reason", FormField("Motivo", self._reason, required=True))
        self.content_layout().addWidget(form)

        self._error = QLabel("", self)
        self._error.setProperty("state", "error")
        self._error.hide()
        self.content_layout().addWidget(self._error)

        box = self.add_button_box(ok_text="Cancelar venta", cancel_text="Volver")
        ok = box.button(QDialogButtonBox.Ok)
        ok.setProperty("variant", "danger")
        ok.setDefault(False)
        box.button(QDialogButtonBox.Cancel).setDefault(True)
        box.accepted.disconnect()
        box.accepted.connect(self._submit)
        self._reason.setFocus()

    def set_reason(self, text: str) -> None:
        self._reason.setText(text)

    def _submit(self) -> None:
        reason = self._reason.value().strip()
        if not reason:
            self._error.setText("Escribe el motivo de la cancelación.")
            self._error.show()
            return
        self.reason = reason
        self.accept()
