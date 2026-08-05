"""Operational origin-purchase workspace backed by canonical Logistics."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QLabel, QSplitter, QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec, PageHeader, SearchInput, SectionCard, StandardLineEdit, StandardTable,
    ViewState, create_primary_button, create_secondary_button, create_state_widget,
    create_success_button,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing

_DOCUMENTS = [ColumnSpec("Documento"), ColumnSpec("Tipo"), ColumnSpec("Proveedor"),
              ColumnSpec("Estado", "status"), ColumnSpec("Líneas"), ColumnSpec("Carga")]
_TREE = [ColumnSpec("Contenedor"), ColumnSpec("Tipo"), ColumnSpec("Estado", "status"),
         ColumnSpec("Peso neto")]
_CONTENTS = [ColumnSpec("Producto"), ColumnSpec("Contenedor"), ColumnSpec("Cantidad"),
             ColumnSpec("Peso"), ColumnSpec("Lote")]
_DIFFERENCES = [ColumnSpec("Producto"), ColumnSpec("Esperado"), ColumnSpec("Cargado"),
                ColumnSpec("Variación"), ColumnSpec("Resultado", "status")]


class LogisticsRelatedPage(QWidget):
    """Choose commercial context, create/open a shipment, and monitor mobile loading."""

    def __init__(self, presenter, parent=None, *, capabilities=None) -> None:
        super().__init__(parent)
        self.setObjectName("originPurchaseWorkspacePage")
        self._presenter = presenter
        self._capabilities = capabilities
        self._documents = []
        self._detail = None
        self._loaded = False
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        root.addWidget(PageHeader(
            title="Compra en origen",
            subtitle="Documento comercial → carga móvil → contenedores → sellado → despacho.",
            icon=Icons.PURCHASES, compact=True))
        self._notice = QLabel("Selecciona un documento habilitado para carga.", self)
        self._notice.setWordWrap(True)
        root.addWidget(self._notice)
        split = QSplitter(Qt.Horizontal, self)
        split.addWidget(self._build_documents())
        split.addWidget(self._build_workspace())
        split.setStretchFactor(0, 35); split.setStretchFactor(1, 65)
        root.addWidget(split, stretch=1)

    def _build_documents(self):
        card = SectionCard(title="Documento comercial")
        self._search = SearchInput(placeholder="Buscar PO, PR, compra directa o proveedor")
        self._search.search_changed.connect(lambda *_: self.reload())
        card.body().addWidget(self._search)
        self._document_table = StandardTable(_DOCUMENTS, self)
        self._document_table.clicked.connect(lambda *_: self._select_document())
        card.body().addWidget(self._document_table)
        self._open = create_primary_button(self, "Crear o abrir embarque")
        self._open.clicked.connect(self._create_or_open)
        self._open.setEnabled(False)
        card.body().addWidget(self._open)
        return card

    def _build_workspace(self):
        card = SectionCard(title="Workspace de carga")
        self._summary = QLabel("Sin embarque seleccionado", self)
        self._summary.setWordWrap(True); card.body().addWidget(self._summary)
        actions = QHBoxLayout()
        self._mobile = create_primary_button(self, "Abrir sesión móvil")
        self._mobile.clicked.connect(self._mobile_handoff)
        refresh = create_secondary_button(self, "Actualizar seguimiento")
        refresh.clicked.connect(self._refresh_detail)
        self._seal_code = StandardLineEdit(self)
        self._seal_code.setPlaceholderText("Código de sello para raíz seleccionada")
        self._seal = create_secondary_button(self, "Sellar raíz")
        self._seal.clicked.connect(self._seal_selected_root)
        self._dispatch = create_success_button(self, "Confirmar despacho")
        self._dispatch.clicked.connect(self._dispatch_shipment)
        for widget in (self._mobile, refresh, self._seal_code, self._seal, self._dispatch):
            actions.addWidget(widget)
        card.body().addLayout(actions)
        self._tree = StandardTable(_TREE, self)
        card.body().addWidget(self._tree)
        lower = QSplitter(Qt.Horizontal, self)
        content_card = SectionCard(title="Asignación de líneas")
        self._contents = StandardTable(_CONTENTS, self); content_card.body().addWidget(self._contents)
        diff_card = SectionCard(title="Diferencias y autorizaciones")
        self._differences = StandardTable(_DIFFERENCES, self)
        diff_card.body().addWidget(self._differences)
        self._authorization = QLabel("Sin autorizaciones pendientes", self)
        self._authorization.setWordWrap(True); diff_card.body().addWidget(self._authorization)
        authorization_row = QHBoxLayout()
        self._authorization_reason = StandardLineEdit(self)
        self._authorization_reason.setPlaceholderText("Motivo de autorización")
        self._authorize = create_secondary_button(self, "Autorizar diferencia seleccionada")
        self._authorize.clicked.connect(self._authorize_selected_difference)
        authorization_row.addWidget(self._authorization_reason, stretch=1)
        authorization_row.addWidget(self._authorize)
        diff_card.body().addLayout(authorization_row)
        lower.addWidget(content_card); lower.addWidget(diff_card)
        card.body().addWidget(lower)
        for widget in (self._mobile, self._seal_code, self._seal, self._dispatch,
                       self._authorization_reason, self._authorize):
            widget.setEnabled(False)
        return card

    def ensure_loaded(self):
        if not self._loaded: self.reload()

    def reload(self):
        try:
            self._documents = self._presenter.origin_documents(self._search.text().strip())
            self._document_table.load_rows([[
                item["document_number"], self._type_label(item["document_type"]),
                item["supplier_name"], item["status"], str(item["line_count"]),
                "Abrir" if item["shipment_id"] else "Por crear",
            ] for item in self._documents], row_ids=[item["id"] for item in self._documents])
            self._loaded = True
        except PermissionError as exc:
            self._documents = []; self._document_table.load_rows([])
            self._feedback(False, str(exc))

    def _select_document(self):
        granted = bool(getattr(self._capabilities, "origin_create", False))
        self._open.setEnabled(granted and bool(self._document_table.selected_row_id()))

    def _selected_document(self):
        selected = self._document_table.selected_row_id()
        return next((item for item in self._documents if item["id"] == selected), None)

    def _create_or_open(self):
        document = self._selected_document()
        if document is None: return
        ok, message, detail = self._presenter.origin_create_shipment(document)
        self._feedback(ok, message)
        if ok:
            document["shipment_id"] = detail["id"]
            self._render_detail(detail); self.reload()

    def _refresh_detail(self):
        if self._detail:
            detail = self._presenter.origin_workspace(self._detail["id"])
            if detail: self._render_detail(detail)

    def _mobile_handoff(self):
        if not self._detail: return
        ok, message, data = self._presenter.origin_mobile_handoff(self._detail["id"])
        if ok:
            QApplication.clipboard().setText(data["url"])
            message += f" Enlace copiado: {data['url']}"
        self._feedback(ok, message)

    def _seal_selected_root(self):
        if not self._detail: return
        node_id = self._tree.selected_row_id()
        node = next((item for item in self._detail["nodes"] if item["id"] == node_id), None)
        code = self._seal_code.text().strip()
        if node is None or node["parent_id"] is not None or not code:
            self._feedback(False, "Selecciona un contenedor raíz y captura el código de sello.")
            return
        ok, message, detail = self._presenter.origin_seal_root(self._detail["id"], node_id, code)
        self._feedback(ok, message)
        if ok: self._seal_code.clear(); self._render_detail(detail)

    def _dispatch_shipment(self):
        if not self._detail: return
        ok, message, detail = self._presenter.origin_dispatch(self._detail["id"])
        self._feedback(ok, message)
        if ok: self._render_detail(detail)

    def _authorize_selected_difference(self):
        if not self._detail: return
        source_line_id = self._differences.selected_row_id()
        reason = self._authorization_reason.text().strip()
        if not source_line_id or not reason:
            self._feedback(False, "Selecciona una diferencia y captura el motivo.")
            return
        ok, message, detail = self._presenter.origin_authorize_variance(
            self._detail["id"], source_line_id, reason)
        self._feedback(ok, message)
        if ok:
            self._authorization_reason.clear(); self._render_detail(detail)

    def _render_detail(self, detail):
        self._detail = detail
        self._summary.setText(
            f"{detail['shipment_number']} · {detail['status']} · versión {detail['version']}\n"
            f"Destino: {detail['destination_branch_id']} / {detail['destination_warehouse_id']} · "
            f"{detail['container_count']} contenedores · {detail['total_quantity']} unidades · "
            f"{detail['net_weight']} kg")
        self._tree.load_rows([[
            f"{'— ' * item['depth']}{item['container_code']}", item["type_name"],
            item["status"], item["net_weight"],
        ] for item in detail["nodes"]], row_ids=[item["id"] for item in detail["nodes"]])
        node_codes = {item["id"]: item["container_code"] for item in detail["nodes"]}
        self._contents.load_rows([[
            item["product_id"], node_codes.get(item["node_id"], "—"), item["quantity"],
            item["net_weight"], item["lot_number"],
        ] for item in detail["contents"]], row_ids=[item["id"] for item in detail["contents"]])
        self._differences.load_rows([[
            item["product_id"], item["expected"], item["loaded"], item["variance"],
            "BLOQUEADA" if item["blocking"] else "PENDIENTE",
        ] for item in detail["differences"]], row_ids=[item["source_line_id"] for item in detail["differences"]])
        pending = detail["pending_authorizations"]
        self._authorization.setText(
            f"{len(pending)} autorización(es) requeridas: " + "; ".join(item["reason"] for item in pending)
            if pending else "Sin autorizaciones pendientes")
        self._authorization.setProperty("state", "BLOCKED" if pending else "READY")
        can_override = bool(getattr(self._capabilities, "origin_override", False))
        self._authorization_reason.setEnabled(bool(pending) and can_override)
        self._authorize.setEnabled(bool(pending) and can_override)
        self._mobile.setEnabled(True)
        can_seal = bool(getattr(self._capabilities, "origin_seal", False))
        self._seal_code.setEnabled(detail["can_seal"] and can_seal)
        self._seal.setEnabled(detail["can_seal"] and can_seal)
        can_dispatch = bool(getattr(self._capabilities, "origin_dispatch", False))
        self._dispatch.setEnabled(detail["can_dispatch"] and can_dispatch)

    def _feedback(self, ok, message):
        self._notice.setProperty("state", "READY" if ok else "ERROR")
        self._notice.setText(message)

    @staticmethod
    def _type_label(value):
        return {"PURCHASE_ORDER": "Orden de compra", "DIRECT_PURCHASE": "Compra directa",
                "PURCHASE_REQUISITION": "Solicitud aprobada"}.get(value, value)
