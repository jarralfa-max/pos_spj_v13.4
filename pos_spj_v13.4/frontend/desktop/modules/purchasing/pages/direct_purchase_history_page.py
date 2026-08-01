"""Master-detail history for direct purchases with contextual mutations."""

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec, PageHeader, SearchInput, SearchableComboBox, SectionCard, StandardTable,
    ViewState, create_danger_button, create_primary_button, create_secondary_button,
    create_state_widget, create_warning_button,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.purchasing.dialogs.direct_purchase_dialogs import (
    HotAuthorizationDialog, ReverseReasonDialog,
)
from frontend.desktop.modules.purchasing.direct_purchase_view_models import money, status_es
from frontend.desktop.themes.tokens import Spacing

_LIST = [ColumnSpec("Folio", "text"), ColumnSpec("Proveedor", "text"),
         ColumnSpec("Estado", "status"), ColumnSpec("Pago", "text"),
         ColumnSpec("Total", "text"), ColumnSpec("Fecha", "text")]
_LINES = [ColumnSpec("Producto", "text"), ColumnSpec("Cantidad", "text"),
          ColumnSpec("Costo", "text"), ColumnSpec("Importe", "text")]


class DirectPurchaseHistoryPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._current_id = None
        self._loaded = False
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        root.addWidget(PageHeader(title="Historial de compra directa",
                                  subtitle="Consulta documental y acciones por estado.",
                                  icon=Icons.PURCHASES, compact=True))
        self._notice = QLabel("Selecciona una compra para consultar su detalle.", self)
        self._notice.setWordWrap(True); root.addWidget(self._notice)
        content = QHBoxLayout(); root.addLayout(content, stretch=1)
        content.addWidget(self._build_master(), stretch=55)
        content.addWidget(self._build_detail(), stretch=45)

    def _build_master(self):
        card = SectionCard(title="Compras directas")
        row = QHBoxLayout()
        self._search = SearchInput(placeholder="Buscar folio")
        self._search.search_changed.connect(lambda *_: self.reload())
        self._status = SearchableComboBox(placeholder="Todos los estados")
        self._status.set_options([("", "Todos"), ("DRAFT", "Borrador"),
                                  ("PENDING_AUTHORIZATION", "Pendiente autorización"),
                                  ("CONFIRMED", "Confirmada"), ("RECEIVED", "Recibida"),
                                  ("REVERSED", "Reversada")])
        self._status.selection_changed.connect(lambda *_: self.reload())
        row.addWidget(self._search, stretch=1); row.addWidget(self._status)
        card.body().addLayout(row)
        self._stack = QStackedWidget(self)
        self._table = StandardTable(_LIST, self)
        self._table.clicked.connect(lambda *_: self._select())
        self._empty = create_state_widget(ViewState.EMPTY, self, message="No hay compras directas")
        self._stack.addWidget(self._table); self._stack.addWidget(self._empty)
        card.body().addWidget(self._stack)
        return card

    def _build_detail(self):
        card = SectionCard(title="Detalle")
        self._summary = QLabel("Sin documento seleccionado", self)
        self._summary.setWordWrap(True); card.body().addWidget(self._summary)
        self._lines = StandardTable(_LINES, self); card.body().addWidget(self._lines)
        actions = QHBoxLayout()
        self._authorize = create_warning_button(self, "Autorizar")
        self._authorize.clicked.connect(self._authorize_current)
        self._confirm = create_primary_button(self, "Confirmar")
        self._confirm.clicked.connect(self._confirm_current)
        self._reverse = create_danger_button(self, "Reversar")
        self._reverse.clicked.connect(self._reverse_current)
        for button in (self._authorize, self._confirm, self._reverse): actions.addWidget(button)
        actions.addStretch(1); card.body().addLayout(actions)
        return card

    def ensure_loaded(self):
        if not self._loaded: self.reload()

    def reload(self):
        model = self._presenter.purchases(status=self._status.current_id() or None,
                                          search=self._search.text().strip())
        self._table.load_rows(model.rows, row_ids=model.row_ids)
        self._stack.setCurrentWidget(self._table if model.rows else self._empty)
        self._loaded = True

    def _select(self):
        self._current_id = self._table.selected_row_id()
        detail = self._presenter.detail(self._current_id) if self._current_id else None
        if detail is None: return
        self._summary.setText(f"{detail.document_number} · {status_es(detail.status)}\n"
                              f"Proveedor: {self._presenter.supplier_name(detail.supplier_id)}\n"
                              f"Total: {money(detail.total)}")
        self._lines.load_rows([[line.description, str(line.quantity), money(line.unit_cost),
                                money(line.line_total)] for line in detail.lines],
                              row_ids=[line.product_id for line in detail.lines])
        caps = self._presenter.capabilities()
        self._authorize.setVisible(caps.direct_authorize and detail.status == "PENDING_AUTHORIZATION")
        self._confirm.setVisible(caps.direct_confirm and detail.status == "DRAFT")
        self._reverse.setVisible(caps.direct_reverse and detail.status in ("CONFIRMED", "RECEIVED"))

    def _authorize_current(self):
        dialog = HotAuthorizationDialog(self)
        if dialog.exec_() and dialog.reason():
            ok, message, _ = self._presenter.authorize(self._current_id, dialog.reason())
            self._feedback(ok, message)

    def _confirm_current(self):
        ok, message, _ = self._presenter.confirm(self._current_id, None)
        self._feedback(ok, message)

    def _reverse_current(self):
        dialog = ReverseReasonDialog(self)
        if dialog.exec_() and dialog.reason():
            ok, message, _ = self._presenter.reverse(self._current_id, dialog.reason())
            self._feedback(ok, message)

    def _feedback(self, ok, message):
        self._notice.setProperty("state", "READY" if ok else "ERROR")
        self._notice.setText(message)
        self.reload(); self._select()
