"""Devoluciones y reversos — puesto de trabajo (auditoría Compras d9f2bca C26).

Antes el backend sabía reversar una recepción, crear/confirmar/cancelar una
devolución y cerrar faltantes, pero ninguna pantalla lo ofrecía: un rechazo o
una reclamación quedaban como datos sin resolución. Aquí, desde la recepción:

* «Reversar recepción» — error de captura: deshace exactamente lo registrado
  (se rechaza si ya hay factura).
* «Devolver al proveedor» — por línea recibida, hasta lo que aún se puede
  devolver; se crea en BORRADOR (no mueve stock).
* «Confirmar devolución» — aquí sale la mercancía y Finanzas aplica la nota de
  crédito; «Cancelar devolución» descarta el borrador.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PyQt5.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components.buttons import (
    create_danger_button,
    create_primary_button,
    create_secondary_button,
    create_success_button,
)
from frontend.desktop.components.dialogs import FormDialog
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.components.worklist_page import WorklistPage

_REASONS = (
    ("QUALITY", "Calidad"), ("DAMAGED", "Dañado"), ("WRONG_PRODUCT", "Producto equivocado"),
    ("EXCESS", "Excedente"), ("EXPIRED", "Caducado"),
    ("SANITARY_FAILURE", "Falla sanitaria"), ("COMMERCIAL_AGREEMENT", "Acuerdo comercial"),
)


class ReturnLinesDialog(FormDialog):
    """Cuánto se devuelve de cada línea recibida y por qué."""

    def __init__(self, parent, lines: list[dict]) -> None:
        super().__init__(parent, title="Devolver al proveedor")
        self._lines = lines
        self._reason = QComboBox(self)
        for code, label in _REASONS:
            self._reason.addItem(label, code)
        self.form.addRow("Motivo", self._reason)
        self._table = StandardTable([
            ColumnSpec("Producto"), ColumnSpec("Disponible", "numeric"),
            ColumnSpec("A devolver", "numeric")], self)
        self._table.load_rows([[ln["product_label"], ln["available"], "0"] for ln in lines],
                              row_ids=[ln["goods_receipt_line_id"] for ln in lines])
        self._table.setEditTriggers(self._table.AllEditTriggers)
        self.form.addRow(self._table)
        self._error = QLabel("", self)
        self._error.setProperty("role", "error")
        self._error.setWordWrap(True)
        self._error.setVisible(False)
        self.form.addRow(self._error)
        self.add_button_box(ok_text="Crear devolución", on_accept=self._accept_if_valid)

    def values(self) -> dict:
        lines = []
        for row, line in enumerate(self._lines):
            item = self._table.item(row, 2)
            try:
                quantity = Decimal((item.text() if item else "0").strip() or "0")
            except InvalidOperation:
                quantity = Decimal("-1")
            if quantity != 0:
                lines.append({"goods_receipt_line_id": line["goods_receipt_line_id"],
                              "product_id": line["product_id"], "quantity": str(quantity)})
        return {"reason": self._reason.currentData(), "lines": lines}

    def _accept_if_valid(self) -> None:
        values = self.values()
        problem = None
        if not values["lines"]:
            problem = "Captura cuánto se devuelve de al menos una línea."
        for line, source in ((ln, next(s for s in self._lines
                                       if s["goods_receipt_line_id"] == ln["goods_receipt_line_id"]))
                             for ln in values["lines"]):
            quantity = Decimal(line["quantity"])
            if quantity <= 0:
                problem = "Las cantidades a devolver deben ser mayores que cero."
            elif quantity > Decimal(source["available"]):
                problem = (f"{source['product_label']}: no se puede devolver más de "
                           f"{source['available']}.")
        if problem:
            self._error.setText(problem)
            self._error.setVisible(True)
            return
        self.accept()


class ReturnsPage(WorklistPage):
    title = "Devoluciones y reversos"
    subtitle = "Recepciones completadas: reverso de captura o devolución al proveedor"
    searchable = False
    paginated = False
    columns = [ColumnSpec("Recepción"), ColumnSpec("Documento"), ColumnSpec("Proveedor"),
               ColumnSpec("Fecha", "date")]
    empty_message = "No hay recepciones completadas"

    def _build_actions(self) -> None:
        capabilities = self._presenter.capabilities()
        self._reverse_button = create_danger_button(self, "Reversar recepción")
        self._reverse_button.setVisible(capabilities.receipt_reverse)
        self._reverse_button.clicked.connect(self._reverse)
        self._return_button = create_primary_button(self, "Devolver al proveedor")
        self._return_button.setVisible(capabilities.return_manage)
        self._return_button.clicked.connect(self._return)
        self.header.add_action(self._reverse_button)
        self.header.add_action(self._return_button)

    def _build_extra(self) -> None:
        capabilities = self._presenter.capabilities()
        box = QWidget(self)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Devoluciones registradas", box))
        self._returns = StandardTable([
            ColumnSpec("Devolución"), ColumnSpec("Recepción"), ColumnSpec("Motivo"),
            ColumnSpec("Estado", "status"), ColumnSpec("Fecha", "date")], box)
        layout.addWidget(self._returns)
        row = QHBoxLayout()
        self._confirm_button = create_success_button(box, "Confirmar devolución")
        self._confirm_button.clicked.connect(self._confirm)
        self._cancel_button = create_secondary_button(box, "Cancelar devolución")
        self._cancel_button.clicked.connect(self._cancel)
        for button in (self._confirm_button, self._cancel_button):
            button.setVisible(capabilities.return_manage)
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        self._layout.addWidget(box)

    def _load(self) -> None:
        self.set_table(self._presenter.completed_receipts())
        model = self._presenter.purchase_returns()
        self._returns.load_rows(model.rows, row_ids=model.row_ids)

    def _ask_reason(self, title: str) -> str | None:
        reason, accepted = FormDialog.get_text(self, title, "Motivo:")
        return reason.strip() if accepted and reason.strip() else None

    def _reverse(self) -> None:
        receipt_id = self._selected()
        if not receipt_id:
            self.notify(False, "Selecciona una recepción.")
            return
        reason = self._ask_reason("Reversar recepción")
        if reason:
            ok, message, _ = self._presenter.reverse_receipt(receipt_id, reason)
            self.notify(ok, message)
            self.reload()

    def _return(self) -> None:
        receipt_id = self._selected()
        if not receipt_id:
            self.notify(False, "Selecciona una recepción.")
            return
        lines = self._presenter.returnable_lines(receipt_id)
        if not lines:
            self.notify(False, "No queda nada por devolver de esa recepción.")
            return
        dialog = ReturnLinesDialog(self, lines)
        if dialog.exec_():
            ok, message, _ = self._presenter.create_return(goods_receipt_id=receipt_id,
                                                           **dialog.values())
            self.notify(ok, message)
            self.reload()

    def _confirm(self) -> None:
        return_id = self._returns.selected_row_id()
        if not return_id:
            self.notify(False, "Selecciona una devolución.")
            return
        ok, message, _ = self._presenter.confirm_return(return_id)
        self.notify(ok, message)
        self.reload()

    def _cancel(self) -> None:
        return_id = self._returns.selected_row_id()
        if not return_id:
            self.notify(False, "Selecciona una devolución.")
            return
        reason = self._ask_reason("Cancelar devolución")
        if reason:
            ok, message, _ = self._presenter.cancel_return(return_id, reason)
            self.notify(ok, message)
            self.reload()
