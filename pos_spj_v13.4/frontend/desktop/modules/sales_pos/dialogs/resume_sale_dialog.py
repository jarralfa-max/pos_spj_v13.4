"""ResumeSaleDialog — elegir qué venta suspendida continuar (§40).

Re-auditoría POS (2026-10-01): "Reanudar" tomaba SIEMPRE la primera de la
lista, sin mostrar nada; con dos clientes esperando no había forma de elegir.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QDialogButtonBox

from frontend.desktop.components import ColumnSpec, StandardDialog, StandardTable
from frontend.desktop.modules.sales_pos.formatting import local_time

_COLUMNS = (
    ColumnSpec("Suspendida", "text"),
    ColumnSpec("Productos", "text"),
    ColumnSpec("Líneas", "numeric"),
    ColumnSpec("Total", "numeric"),
)


def _hora(stamp: str | None) -> str:
    return local_time(stamp)


def _resumen(sale) -> str:
    nombres = [str(line.product_snapshot.get("name") or "") for line in sale.lines]
    texto = ", ".join(n for n in nombres if n)
    return texto if len(texto) <= 48 else texto[:45] + "..."


class ResumeSaleDialog(StandardDialog):
    def __init__(self, suspended_sales, parent=None) -> None:
        super().__init__(parent, title="Reanudar venta suspendida", width=640)
        self.setObjectName("posResumeDialog")
        self.sale_id: str | None = None
        self._sales = list(suspended_sales)

        self._table = StandardTable(list(_COLUMNS), self)
        self._table.setObjectName("posSuspendedTable")
        self._table.load_rows(
            [[_hora(s.suspended_at), _resumen(s), str(len(s.lines)), f"${s.total:,.2f}"]
             for s in self._sales],
            row_ids=[s.id for s in self._sales])
        self._table.itemDoubleClicked.connect(lambda _item: self._submit())
        if self._sales:
            self._table.selectRow(0)
        self.content_layout().addWidget(self._table)

        box = self.add_button_box(ok_text="Reanudar")
        box.accepted.disconnect()
        box.accepted.connect(self._submit)
        self._ok = box.button(QDialogButtonBox.Ok)

    def focus_sale(self, sale_id: str) -> None:
        for row, sale in enumerate(self._sales):
            if sale.id == sale_id:
                self._table.selectRow(row)
                return

    def _submit(self) -> None:
        sale_id = self._table.selected_row_id()
        if sale_id:
            self.sale_id = sale_id
            self.accept()
