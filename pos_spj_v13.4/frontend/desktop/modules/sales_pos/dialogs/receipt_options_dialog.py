"""PostedSalePickerDialog — elegir una venta YA COBRADA (reimprimir, facturar,
devolver).

Re-auditoría POS (2026-10-01): Reimprimir (F12) y Factura (F11) actuaban sobre
`self._sale_id`, que después de cobrar es la venta NUEVA, vacía: reimprimir
fallaba siempre con "nunca completó el cobro" y la factura se pedía para una
venta sin nada. Ahora se elige la venta: la más reciente viene seleccionada
(es casi siempre la que se busca) y se puede buscar por folio.

La reimpresión exige motivo (§48: "registrar motivo"); facturar no.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QDialogButtonBox, QHBoxLayout, QLabel

from frontend.desktop.components import (
    ColumnSpec,
    FormField,
    SearchInput,
    StandardDialog,
    StandardForm,
    StandardLineEdit,
    StandardTable,
)
from frontend.desktop.modules.sales_pos.formatting import local_time

STATUS_LABELS = {
    "COMPLETED": "Cobrada", "RETURNED_PARTIALLY": "Devolución parcial",
    "RETURNED_FULLY": "Devuelta", "REVERSED": "Reversada",
}
_COLUMNS = (
    ColumnSpec("Folio", "text"),
    ColumnSpec("Hora", "text"),
    ColumnSpec("Estado", "text"),
    ColumnSpec("Total", "numeric"),
)


def folio_of(sale) -> str:
    return sale.sale_number or f"…{sale.id[-8:]}"


class PostedSalePickerDialog(StandardDialog):
    def __init__(self, presenter, *, title: str, ok_text: str, ask_reason: bool = False,
                 default_reason: str = "", parent=None) -> None:
        super().__init__(parent, title=title, width=640)
        self.setObjectName("posPostedSalePicker")
        self._presenter = presenter
        self.sale = None
        self.reason: str | None = None
        self._sales = list(presenter.recent_posted_sales())

        search_row = QHBoxLayout()
        self._search = SearchInput(self, placeholder="Folio, p. ej. V-COR-000123")
        self._search.search_submitted.connect(self._find_by_folio)
        search_row.addWidget(self._search)
        self.content_layout().addLayout(search_row)

        self._table = StandardTable(list(_COLUMNS), self)
        self._table.setObjectName("posPostedSalesTable")
        self._table.itemDoubleClicked.connect(lambda _item: self._submit())
        self.content_layout().addWidget(self._table)
        self._load(self._sales)

        self._empty = QLabel("No hay ventas cobradas en esta sucursal.", self)
        self._empty.setProperty("role", "empty")
        self._empty.setVisible(not self._sales)
        self.content_layout().addWidget(self._empty)

        self._reason = None
        if ask_reason:
            form = StandardForm(self)
            self._reason = StandardLineEdit(self, placeholder="Por qué se reimprime")
            self._reason.setText(default_reason)
            form.add_field("reason", FormField("Motivo", self._reason, required=True))
            self.content_layout().addWidget(form)

        self._error = QLabel("", self)
        self._error.setProperty("state", "error")
        self._error.setWordWrap(True)
        self._error.hide()
        self.content_layout().addWidget(self._error)

        box = self.add_button_box(ok_text=ok_text)
        box.accepted.disconnect()
        box.accepted.connect(self._submit)
        self._ok = box.button(QDialogButtonBox.Ok)

    def _load(self, sales) -> None:
        self._table.load_rows(
            [[folio_of(s), local_time(s.completed_at),
              STATUS_LABELS.get(s.status, s.status), f"${s.total:,.2f}"] for s in sales],
            row_ids=[s.id for s in sales])
        if sales:
            self._table.selectRow(0)

    def _find_by_folio(self, text: str) -> None:
        sale = self._presenter.find_posted_sale(text)
        if sale is None:
            self._error.setText(f"No hay una venta cobrada con el folio «{text.strip()}» "
                                "en esta sucursal.")
            self._error.show()
            return
        self._error.hide()
        if all(s.id != sale.id for s in self._sales):
            self._sales.insert(0, sale)
        self._load([sale] + [s for s in self._sales if s.id != sale.id])

    def focus_sale(self, sale_id: str) -> None:
        for row in range(self._table.rowCount()):
            self._table.selectRow(row)
            if self._table.selected_row_id() == sale_id:
                return

    def set_reason(self, text: str) -> None:
        if self._reason is not None:
            self._reason.setText(text)

    def _submit(self) -> None:
        sale_id = self._table.selected_row_id()
        sale = next((s for s in self._sales if s.id == sale_id), None)
        if sale is None:
            self._error.setText("Elige una venta.")
            self._error.show()
            return
        if self._reason is not None:
            reason = self._reason.value().strip()
            if not reason:
                self._error.setText("Escribe el motivo.")
                self._error.show()
                return
            self.reason = reason
        self.sale = sale
        self.accept()
