"""InvoiceStatusDialog — estado de las facturas de una venta (auditoría V09).

Antes el POS sólo REGISTRABA la solicitud y decía «Fiscal la timbra»: nadie veía
después si se timbró o falló. Aquí se ve cada solicitud con su estado
(Solicitada / Timbrada con su folio fiscal / Error con su motivo) y, mientras no
exista integración con un PAC, quien timbra fuera del sistema registra el
resultado: el UUID del timbre o el error. Tras un error se puede pedir de nuevo.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem,QWidget,
)

from frontend.desktop.components import (
    StandardDialog,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.dialogs import MessageDialog

STATUS_LABELS = {"REQUESTED": "Solicitada", "ISSUED": "Timbrada", "ERROR": "Con error"}


def describe(request) -> str:
    text = (f"{STATUS_LABELS.get(request.status, request.status)} · {request.tax_identifier} · "
            f"{request.legal_name} · uso {request.cfdi_use} · {request.requested_at[:10]}")
    if request.uuid_fiscal:
        text += f" · folio fiscal {request.uuid_fiscal}"
    if request.error_message:
        text += f" · {request.error_message}"
    return text


class InvoiceStatusDialog(StandardDialog):
    def __init__(self, presenter, *, sale, folio: str, parent=None) -> None:
        super().__init__(parent, title=f"Facturas — venta {folio}", width=720)
        self.setObjectName("posInvoiceStatusDialog")
        self._presenter = presenter
        self._sale = sale
        self.new_request = False
        self.changed = False

        hint = QLabel("Mientras no haya un PAC conectado, registra aquí el resultado del "
                      "timbrado que se hizo fuera del sistema.", self)
        hint.setWordWrap(True)
        hint.setProperty("role", "subtitle")
        self.content_layout().addWidget(hint)

        self._list = QListWidget(self)
        self._list.setObjectName("posInvoiceRequests")
        self.content_layout().addWidget(self._list, stretch=1)

        row = QWidget(self)
        actions = QHBoxLayout(row)
        actions.setContentsMargins(0, 0, 0, 0)
        self._btn_issued = create_secondary_button(self, "Registrar timbrado")
        self._btn_issued.clicked.connect(self._register_issued)
        actions.addWidget(self._btn_issued)
        self._btn_error = create_secondary_button(self, "Registrar error")
        self._btn_error.clicked.connect(self._register_error)
        actions.addWidget(self._btn_error)
        self._btn_new = create_primary_button(self, "Nueva solicitud")
        self._btn_new.clicked.connect(self._ask_new)
        actions.addWidget(self._btn_new)
        self.content_layout().addWidget(row)
        self._list.currentRowChanged.connect(lambda _row: self._sync_buttons())
        self._render()

    def _requests(self):
        return list(self._sale.invoice_requests or ())

    def _render(self) -> None:
        self._list.clear()
        for request in self._requests():
            self._list.addItem(QListWidgetItem(describe(request)))
        pending = [i for i, r in enumerate(self._requests()) if r.status == "REQUESTED"]
        self._list.setCurrentRow(pending[0] if pending else max(0, self._list.count() - 1))
        self._sync_buttons()

    def _selected(self):
        row = self._list.currentRow()
        requests = self._requests()
        return requests[row] if 0 <= row < len(requests) else None

    def _sync_buttons(self) -> None:
        selected = self._selected()
        pending = selected is not None and selected.status == "REQUESTED"
        self._btn_issued.setEnabled(pending)
        self._btn_error.setEnabled(pending)
        self._btn_new.setEnabled(not any(r.status == "REQUESTED" for r in self._requests()))

    def _ask(self, title: str, label: str, placeholder: str) -> str | None:
        from frontend.desktop.modules.sales_pos.dialogs.cancel_sale_dialog import (
            CancelSaleDialog,
        )
        dialog = CancelSaleDialog(title=title, ok_text="Registrar", message=label, parent=self)
        dialog._reason.setPlaceholderText(placeholder)   # mismo campo de texto obligatorio
        if not dialog.exec_() or not dialog.reason:
            return None
        return dialog.reason

    def _apply(self, result) -> None:
        if not result.success:
            MessageDialog.warning(self, "No se registró", result.message)
            return
        self._sale = result.data.get("sale") or self._sale
        self.changed = True
        self._render()

    def _register_issued(self) -> None:
        selected = self._selected()
        if selected is None:
            return
        uuid = self._ask("Registrar timbrado", "Folio fiscal (UUID) del timbre del SAT.",
                         "XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX")
        if uuid:
            self._apply(self._presenter.mark_invoice_issued(
                sale_id=self._sale.id, invoice_request_id=selected.id, uuid_fiscal=uuid))

    def _register_error(self) -> None:
        selected = self._selected()
        if selected is None:
            return
        reason = self._ask("Registrar error", "Qué respondió el PAC o el SAT.",
                           "Motivo del rechazo")
        if reason:
            self._apply(self._presenter.mark_invoice_error(
                sale_id=self._sale.id, invoice_request_id=selected.id, error_message=reason))

    def _ask_new(self) -> None:
        self.new_request = True
        self.accept()
