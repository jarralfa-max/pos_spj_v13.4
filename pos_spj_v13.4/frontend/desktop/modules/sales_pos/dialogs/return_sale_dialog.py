"""ReturnSaleDialog — devolución de una venta cobrada (§43-44, F10).

Re-auditoría POS (2026-10-01): el botón Devolución y F10 emitían una señal que
NADIE escuchaba; los casos de uso de devolver línea y reversar venta existían y
no tenían ningún llamador en la pantalla. Este diálogo es ese llamador:

1. elige la venta cobrada (la más reciente seleccionada, o por folio);
2. elige la línea y la cantidad a devolver (se muestra lo que aún se puede
   devolver; el dominio rechaza devolver de más);
3. motivo y autorización de OTRO usuario con usuario y clave — verificada con
   el mismo estándar que el login, y su permiso lo decide el caso de uso (§62:
   el cajero no autoriza su propia devolución);
4. "Devolver" (una línea) o "Reversar venta completa" (todo, sin tocar la
   venta original: el reverso es una transacción propia, §44).

La mercancía vuelve al inventario por el caso de uso (al lote del que salió).
"""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtWidgets import QHBoxLayout, QLabel

from frontend.desktop.components import (
    ColumnSpec,
    FormField,
    PasswordInput,
    QuantityInput,
    SearchInput,
    StandardDialog,
    StandardForm,
    StandardLineEdit,
    StandardTable,
    create_danger_button,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.modules.sales_pos.components.cart_table import format_quantity
from frontend.desktop.modules.sales_pos.dialogs.receipt_options_dialog import (
    STATUS_LABELS,
    folio_of,
)
from frontend.desktop.modules.sales_pos.formatting import local_time

_SALE_COLUMNS = (
    ColumnSpec("Folio", "text", min_width=110, preferred_width=130, stretch=False),
    ColumnSpec("Hora", "text", min_width=120, preferred_width=140, stretch=False),
    ColumnSpec("Estado", "text", min_width=100, preferred_width=140, stretch=True),
    ColumnSpec("Total", "numeric", min_width=80, preferred_width=100, stretch=False),
)
_LINE_COLUMNS = (
    ColumnSpec("Producto", "text", min_width=120, preferred_width=160, stretch=True),
    ColumnSpec("Vendido", "numeric", min_width=70, preferred_width=80, stretch=False),
    ColumnSpec("Por devolver", "numeric", min_width=90, preferred_width=100, stretch=False),
    ColumnSpec("Ud.", "text", min_width=40, preferred_width=48, stretch=False),
    ColumnSpec("Importe", "numeric", min_width=80, preferred_width=90, stretch=False),
)


class ReturnSaleDialog(StandardDialog):
    def __init__(self, presenter, *, can_reverse: bool = False, parent=None) -> None:
        super().__init__(parent, title="Devolución", width=760)
        self.setObjectName("posReturnDialog")
        self._presenter = presenter
        self._sales = list(presenter.recent_posted_sales())
        self._sale = None
        self.changed = False

        search_row = QHBoxLayout()
        self._search = SearchInput(self, placeholder="Folio de la venta, p. ej. V-COR-000123")
        self._search.search_submitted.connect(self._find_by_folio)
        search_row.addWidget(self._search)
        self.content_layout().addLayout(search_row)

        self._sales_table = StandardTable(list(_SALE_COLUMNS), self)
        self._sales_table.setObjectName("posReturnSales")
        self._sales_table.setMaximumHeight(170)
        self._sales_table.itemSelectionChanged.connect(self._on_sale_selected)
        self.content_layout().addWidget(self._sales_table)

        self._lines_table = StandardTable(list(_LINE_COLUMNS), self)
        self._lines_table.setObjectName("posReturnLines")
        self._lines_table.itemSelectionChanged.connect(self._on_line_selected)
        self.content_layout().addWidget(self._lines_table)

        form = StandardForm(self)
        self._quantity = QuantityInput(self, decimals=3)
        form.add_field("quantity", FormField("Cantidad a devolver", self._quantity, required=True))
        self._reason = StandardLineEdit(self, placeholder="Por qué se devuelve")
        form.add_field("reason", FormField("Motivo", self._reason, required=True))
        self._authorizer = StandardLineEdit(self, placeholder="Usuario de quien autoriza")
        form.add_field("authorizer", FormField(
            "Autoriza", self._authorizer, required=True,
            helper="Otro usuario con permiso de devolución; no puede ser quien cobra"))
        self._password = PasswordInput(self, placeholder="Clave de quien autoriza")
        form.add_field("password", FormField("Clave", self._password, required=True))
        self.content_layout().addWidget(form)

        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        self._status.hide()
        self.content_layout().addWidget(self._status)

        actions = QHBoxLayout()
        self.btn_return = create_primary_button(self, "Devolver línea")
        self.btn_return.clicked.connect(self._return_line)
        actions.addWidget(self.btn_return)
        self.btn_reverse = create_danger_button(self, "Reversar venta completa")
        self.btn_reverse.setEnabled(can_reverse)
        self.btn_reverse.clicked.connect(self._reverse)
        actions.addWidget(self.btn_reverse)
        actions.addStretch(1)
        close = create_secondary_button(self, "Cerrar")
        close.clicked.connect(self.accept)
        actions.addWidget(close)
        self.content_layout().addLayout(actions)

        self._load_sales(self._sales)

    # ── selección ────────────────────────────────────────────────────────
    def _load_sales(self, sales) -> None:
        self._sales_table.load_rows(
            [[folio_of(s), local_time(s.completed_at),
              STATUS_LABELS.get(s.status, s.status), f"${s.total:,.2f}"] for s in sales],
            row_ids=[s.id for s in sales])
        if sales:
            self._sales_table.selectRow(0)
        else:
            self._show("No hay ventas cobradas en esta sucursal.", error=False)
            self._sale = None
            self._load_lines()

    def _find_by_folio(self, text: str) -> None:
        sale = self._presenter.find_posted_sale(text)
        if sale is None:
            self._show(f"No hay una venta cobrada con el folio «{text.strip()}».")
            return
        self._sales = [sale] + [s for s in self._sales if s.id != sale.id]
        self._load_sales(self._sales)

    def select_sale(self, sale_id: str) -> None:
        for row in range(self._sales_table.rowCount()):
            self._sales_table.selectRow(row)
            if self._sales_table.selected_row_id() == sale_id:
                return

    def select_line(self, line_id: str) -> None:
        for row in range(self._lines_table.rowCount()):
            self._lines_table.selectRow(row)
            if self._lines_table.selected_row_id() == line_id:
                return

    def fill(self, *, quantity: Decimal, reason: str, authorizer: str, password: str) -> None:
        self._quantity.set_decimal_value(quantity)
        self._reason.setText(reason)
        self._authorizer.setText(authorizer)
        self._password.setText(password)

    def _on_sale_selected(self) -> None:
        sale_id = self._sales_table.selected_row_id()
        self._sale = next((s for s in self._sales if s.id == sale_id), None)
        self._load_lines()

    def _load_lines(self) -> None:
        sale = self._sale
        lines = list(sale.lines) if sale else []
        self._lines_table.load_rows(
            [[str(l.product_snapshot.get("name") or l.product_id), format_quantity(l.quantity),
              format_quantity(sale.returnable_quantity(l.id)), l.quantity_unit,
              f"${l.line_total:,.2f}"] for l in lines],
            row_ids=[l.id for l in lines])
        if lines:
            self._lines_table.selectRow(0)

    def _on_line_selected(self) -> None:
        line_id = self._lines_table.selected_row_id()
        if self._sale and line_id:
            self._quantity.set_decimal_value(self._sale.returnable_quantity(line_id))

    # ── acciones ─────────────────────────────────────────────────────────
    def _show(self, message: str, *, error: bool = True) -> None:
        self._status.setProperty("state", "error" if error else "success")
        self._status.setText(message)
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)
        self._status.show()

    def _authorize(self) -> tuple[str | None, str]:
        reason = self._reason.value().strip()
        if not reason:
            return None, "Escribe el motivo de la devolución."
        usuario = self._authorizer.value().strip()
        if not usuario:
            return None, "Una devolución necesita la autorización de otro usuario."
        user_id, motivo = self._presenter.verify_authorizer(usuario, self._password.value())
        return user_id, motivo

    def _return_line(self) -> None:
        line_id = self._lines_table.selected_row_id()
        if self._sale is None or not line_id:
            self._show("Elige la venta y la línea a devolver.")
            return
        authorizer, problem = self._authorize()
        if authorizer is None:
            self._show(problem)
            return
        result = self._presenter.return_line(
            sale_id=self._sale.id, line_id=line_id, quantity=self._quantity.decimal_value(),
            reason=self._reason.value().strip(), authorizer_user_id=authorizer)
        self._after(result, f"Devolución registrada por ${result.data.get('amount', 0):,.2f}."
                    if result.success else "")

    def _reverse(self) -> None:
        if self._sale is None:
            self._show("Elige la venta a reversar.")
            return
        authorizer, problem = self._authorize()
        if authorizer is None:
            self._show(problem)
            return
        result = self._presenter.reverse_sale(
            sale_id=self._sale.id, reason=self._reason.value().strip(),
            authorizer_user_id=authorizer)
        self._after(result, "Venta reversada: la mercancía volvió al inventario.")

    def _after(self, result, ok_message: str) -> None:
        if not result.success:
            self._show(result.message)
            return
        self.changed = True
        self._password.clear()
        refreshed = result.data.get("sale")
        if refreshed is not None:
            self._sales = [refreshed if s.id == refreshed.id else s for s in self._sales]
            self._load_sales(self._sales)
            self.select_sale(refreshed.id)
        self._show(ok_message, error=False)
