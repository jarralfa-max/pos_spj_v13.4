"""Operational origin-purchase workspace backed by canonical Logistics.

FASE 8-10 (2026-09-29): el escritorio opera el flujo completo (antes sólo
prometía una "sesión móvil"): origen = bodega del proveedor → contenedores
(registrar, buscar por código o QR, padre/hijo) → cargar líneas con peso, lote,
caducidad y temperatura según el producto → sellar → despachar → tránsito →
llegada → conteo/pesaje → recepción de la compra → inventario → cierre.
Todo pasa por el presentador; nombres y estados en español, nunca ids.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QLabel, QSplitter, QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec, PageHeader, SearchInput, SectionCard, StandardCheckBox, StandardLineEdit,
    StandardTable, Tabs, create_primary_button, create_secondary_button,
    create_success_button,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.purchasing.dialogs.origin_dialogs import (
    ArrivalCountDialog, ContainerRegisterDialog, LoadLineDialog, OriginPickDialog,
)
from frontend.desktop.themes.tokens import Spacing

_DOCUMENTS = [ColumnSpec("Documento"), ColumnSpec("Tipo"), ColumnSpec("Proveedor"),
              ColumnSpec("Recoger en"), ColumnSpec("Estado", "status"), ColumnSpec("Líneas"),
              ColumnSpec("Carga")]
_TREE = [ColumnSpec("Contenedor"), ColumnSpec("Tipo"), ColumnSpec("Estado", "status"),
         ColumnSpec("Peso neto")]
_CONTENTS = [ColumnSpec("Producto"), ColumnSpec("Contenedor"), ColumnSpec("Cantidad"),
             ColumnSpec("Peso"), ColumnSpec("Lote")]
_DIFFERENCES = [ColumnSpec("Producto"), ColumnSpec("Esperado"), ColumnSpec("Cargado"),
                ColumnSpec("Variación"), ColumnSpec("Resultado", "status")]
_ARRIVAL = [ColumnSpec("Producto"), ColumnSpec("Contenedor"), ColumnSpec("Declarado"),
            ColumnSpec("Recibido"), ColumnSpec("Aceptado"), ColumnSpec("Peso real")]

SHIPMENT_STATUS_ES = {
    "DRAFT": "Borrador", "LOADING": "Cargando", "READY_TO_SEAL": "Por sellar",
    "SEALED": "Sellado", "DISPATCHED": "Despachado", "IN_TRANSIT": "En tránsito",
    "ARRIVED": "En destino", "RECEIVING": "Recibiendo", "PARTIALLY_RECEIVED": "Recibido parcial",
    "RECEIVED": "Recibido", "CANCELLED": "Cancelado", "CLOSED": "Cerrado",
}
NODE_STATUS_ES = {
    "EXPECTED": "Esperado", "LOADING": "Cargando", "SEALED": "Sellado", "ARRIVED": "En destino",
    "OPENED": "Abierto", "COUNTED": "Contado", "ACCEPTED": "Aceptado",
    "PARTIALLY_ACCEPTED": "Aceptado parcial", "REJECTED": "Rechazado", "MISSING": "Faltante",
    "DAMAGED": "Dañado", "QUARANTINED": "En cuarentena", "RELEASED": "Liberado",
}
DOCUMENT_STATUS_ES = {
    "APPROVED": "Aprobada", "SENT": "Enviada", "ACKNOWLEDGED": "Confirmada",
    "PARTIALLY_LOADED": "Carga parcial", "DRAFT": "Borrador", "CONFIRMED": "Confirmada",
    "PARTIALLY_SOURCED": "Abastecida parcial",
}


class LogisticsRelatedPage(QWidget):
    """Choose commercial context, create/open a shipment, load, dispatch and receive."""

    def __init__(self, presenter, parent=None, *, capabilities=None) -> None:
        super().__init__(parent)
        self.setObjectName("originPurchaseWorkspacePage")
        self._presenter = presenter
        self._capabilities = capabilities
        self._documents = []
        self._detail = None
        self._arrival = []
        self._loaded = False
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        root.addWidget(PageHeader(
            title="Compra en origen",
            subtitle="Bodega del proveedor → contenedores → sellado → despacho → llegada → "
                     "recepción → inventario.",
            icon=Icons.PURCHASES, compact=True))
        self._notice = QLabel("Selecciona un documento habilitado para carga.", self)
        self._notice.setProperty("role", "banner")
        self._notice.setWordWrap(True)
        root.addWidget(self._notice)
        split = QSplitter(Qt.Horizontal, self)
        split.addWidget(self._build_documents())
        split.addWidget(self._build_workspace())
        split.setStretchFactor(0, 35); split.setStretchFactor(1, 65)
        root.addWidget(split, stretch=1)

    def _can(self, name: str) -> bool:
        return bool(getattr(self._capabilities, name, False))

    def _build_documents(self):
        card = SectionCard(title="Documento comercial")
        self._search = SearchInput(placeholder="Buscar OC, compra directa o proveedor")
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

        containers = QHBoxLayout()
        self._register = create_secondary_button(self, "Registrar contenedor")
        self._register.clicked.connect(self._register_container)
        self._container_ref = StandardLineEdit(self)
        self._container_ref.setPlaceholderText("Código o QR del contenedor")
        self._container_ref.returnPressed.connect(self._attach_container)
        self._inside = StandardCheckBox("Dentro del seleccionado", self)
        self._attach = create_secondary_button(self, "Agregar al embarque")
        self._attach.clicked.connect(self._attach_container)
        self._load = create_primary_button(self, "Cargar línea")
        self._load.clicked.connect(self._load_line)
        for widget in (self._register, self._container_ref, self._inside, self._attach,
                       self._load):
            containers.addWidget(widget)
        card.body().addLayout(containers)

        actions = QHBoxLayout()
        self._mobile = create_secondary_button(self, "Abrir sesión móvil")
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
        # Pestañas: con carga, diferencias y llegada apiladas la página no cabía
        # en 1366×768.
        self._tabs = Tabs(self)
        content_tab = QWidget(self)
        content_layout = QVBoxLayout(content_tab)
        self._contents = StandardTable(_CONTENTS, self); content_layout.addWidget(self._contents)
        diff_tab = QWidget(self)
        diff_layout = QVBoxLayout(diff_tab)
        self._differences = StandardTable(_DIFFERENCES, self)
        diff_layout.addWidget(self._differences)
        self._authorization = QLabel("Sin autorizaciones pendientes", self)
        self._authorization.setWordWrap(True); diff_layout.addWidget(self._authorization)
        authorization_row = QHBoxLayout()
        self._authorization_reason = StandardLineEdit(self)
        self._authorization_reason.setPlaceholderText("Motivo de autorización")
        self._authorize = create_secondary_button(self, "Autorizar diferencia seleccionada")
        self._authorize.clicked.connect(self._authorize_selected_difference)
        authorization_row.addWidget(self._authorization_reason, stretch=1)
        authorization_row.addWidget(self._authorize)
        diff_layout.addLayout(authorization_row)

        arrival_tab = QWidget(self)
        arrival_layout = QVBoxLayout(arrival_tab)
        arrival_actions = QHBoxLayout()
        self._transit = create_secondary_button(self, "Marcar en tránsito")
        self._transit.clicked.connect(self._mark_in_transit)
        self._arrive = create_secondary_button(self, "Registrar llegada")
        self._arrive.clicked.connect(self._register_arrival)
        self._count = create_secondary_button(self, "Contar seleccionado")
        self._count.clicked.connect(self._count_selected)
        self._receive = create_success_button(self, "Recibir y cerrar embarque")
        self._receive.clicked.connect(self._receive_and_close)
        for widget in (self._transit, self._arrive, self._count, self._receive):
            arrival_actions.addWidget(widget)
        arrival_actions.addStretch(1)
        arrival_layout.addLayout(arrival_actions)
        self._arrival_table = StandardTable(_ARRIVAL, self)
        arrival_layout.addWidget(self._arrival_table)
        self._tabs.addTab(content_tab, "Asignación de líneas")
        self._tabs.addTab(diff_tab, "Diferencias y autorizaciones")
        self._tabs.addTab(arrival_tab, "Llegada y recepción")
        card.body().addWidget(self._tabs, stretch=1)
        self._disable_all()
        return card

    def _disable_all(self):
        for widget in (self._register, self._container_ref, self._inside, self._attach,
                       self._load, self._mobile, self._seal_code, self._seal, self._dispatch,
                       self._authorization_reason, self._authorize, self._transit, self._arrive,
                       self._count, self._receive):
            widget.setEnabled(False)

    def ensure_loaded(self):
        if not self._loaded: self.reload()

    def reload(self):
        try:
            self._documents = self._presenter.origin_documents(self._search.text().strip())
            self._document_table.load_rows([[
                item["document_number"], self._type_label(item["document_type"]),
                item["supplier_name"], item.get("origin_display") or "Por elegir",
                DOCUMENT_STATUS_ES.get(item["status"], item["status"]),
                str(item["line_count"]), "Abrir" if item["shipment_id"] else "Por crear",
            ] for item in self._documents], row_ids=[item["id"] for item in self._documents])
            self._loaded = True
        except PermissionError as exc:
            self._documents = []; self._document_table.load_rows([])
            self._feedback(False, str(exc))

    def _select_document(self):
        self._open.setEnabled(self._can("origin_create")
                              and bool(self._document_table.selected_row_id()))

    def _selected_document(self):
        selected = self._document_table.selected_row_id()
        return next((item for item in self._documents if item["id"] == selected), None)

    def _create_or_open(self):
        document = self._selected_document()
        if document is None: return
        origin_id = None
        if not document.get("shipment_id") and not document.get("origin_supplier_address_id"):
            options = self._presenter.origin_supplier_options(document.get("supplier_id"))
            if len(options) > 1:
                dialog = OriginPickDialog(self, options=options)
                if not dialog.exec_():
                    return
                origin_id = dialog.origin_id()
        ok, message, detail = self._presenter.origin_create_shipment(document, origin_id)
        self._feedback(ok, "Embarque listo para cargar." if ok else message)
        if ok:
            document["shipment_id"] = detail["id"]
            self._render_detail(detail); self.reload()

    def _refresh_detail(self):
        if self._detail:
            detail = self._presenter.origin_workspace(self._detail["id"])
            if detail: self._render_detail(detail)

    def _after(self, ok, message, detail, success_text):
        self._feedback(ok, success_text if ok else message)
        if ok and detail:
            self._render_detail(detail)

    # ── contenedores ──────────────────────────────────────────────────────────
    def _register_container(self):
        dialog = ContainerRegisterDialog(self, type_options=self._presenter.origin_container_types())
        if not dialog.exec_():
            return
        type_id = None
        if dialog.creates_type():
            ok, message, data = self._presenter.origin_register_container_type(
                **dialog.type_values())
            if not ok:
                self._feedback(False, message); return
            type_id = data.get("id")
        values = dialog.container_values(type_id)
        ok, message, _data = self._presenter.origin_register_container(**values)
        self._feedback(ok, f"Contenedor {values['code'].upper()} registrado." if ok else message)
        if ok:
            self._container_ref.setText(values["code"].upper())

    def _attach_container(self):
        if not self._detail: return
        reference = self._container_ref.text().strip()
        if not reference:
            self._feedback(False, "Captura o escanea el código del contenedor."); return
        parent = self._tree.selected_row_id() if self._inside.isChecked() else None
        ok, message, detail = self._presenter.origin_attach_container(
            self._detail["id"], reference, parent)
        self._after(ok, message, detail, f"Contenedor {reference.upper()} agregado.")
        if ok:
            self._container_ref.clear()

    def _load_line(self):
        if not self._detail: return
        node_id = self._tree.selected_row_id()
        node = next((n for n in self._detail["nodes"] if n["id"] == node_id), None)
        if node is None:
            self._feedback(False, "Selecciona el contenedor donde se carga."); return
        lines = self._presenter.origin_loading_lines(self._detail["id"])
        if not lines:
            self._feedback(False, "El documento no tiene líneas para cargar."); return
        dialog = LoadLineDialog(self, lines=lines, container_label=node["container_code"])
        if not dialog.exec_():
            return
        ok, message, detail = self._presenter.origin_assign_line(
            self._detail["id"], node_id=node_id, **dialog.values())
        self._after(ok, message, detail, "Línea cargada.")

    # ── sellado / despacho ────────────────────────────────────────────────────
    def _mobile_handoff(self):
        if not self._detail: return
        ok, message, data = self._presenter.origin_mobile_handoff(self._detail["id"])
        if ok:
            QApplication.clipboard().setText(data["url"])
            message = f"Enlace de la sesión móvil copiado: {data['url']}"
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
        self._after(ok, message, detail, f"Contenedor sellado con {code}.")
        if ok: self._seal_code.clear()

    def _dispatch_shipment(self):
        if not self._detail: return
        ok, message, detail = self._presenter.origin_dispatch(self._detail["id"])
        self._after(ok, message, detail, "Embarque despachado.")

    def _authorize_selected_difference(self):
        if not self._detail: return
        source_line_id = self._differences.selected_row_id()
        reason = self._authorization_reason.text().strip()
        if not source_line_id or not reason:
            self._feedback(False, "Selecciona una diferencia y captura el motivo.")
            return
        ok, message, detail = self._presenter.origin_authorize_variance(
            self._detail["id"], source_line_id, reason)
        self._after(ok, message, detail, "Diferencia autorizada.")
        if ok: self._authorization_reason.clear()

    # ── llegada y recepción ───────────────────────────────────────────────────
    def _mark_in_transit(self):
        if not self._detail: return
        ok, message, detail = self._presenter.origin_mark_in_transit(self._detail["id"])
        self._after(ok, message, detail, "Embarque en tránsito.")

    def _register_arrival(self):
        if not self._detail: return
        ok, message, detail = self._presenter.origin_register_arrival(self._detail["id"])
        self._after(ok, message, detail, "Llegada registrada: cuenta y pesa cada contenido.")

    def _count_selected(self):
        if not self._detail: return
        content_id = self._arrival_table.selected_row_id()
        line = next((ln for ln in self._arrival if ln["content_id"] == content_id), None)
        if line is None:
            self._feedback(False, "Selecciona el contenido que vas a contar."); return
        dialog = ArrivalCountDialog(self, line=line)
        if not dialog.exec_():
            return
        ok, message, detail = self._presenter.origin_record_count(
            self._detail["id"], **dialog.values())
        self._after(ok, message, detail, f"Conteo de {line['product_name']} guardado.")

    def _receive_and_close(self):
        if not self._detail: return
        ok, message, detail = self._presenter.origin_receive_and_close(self._detail["id"])
        receipts = ", ".join(str(r) for r in (detail or {}).get("receipts", []) if r)
        self._after(ok, message, detail,
                    f"Mercancía recibida ({receipts}) y embarque cerrado." if receipts
                    else "Embarque recibido y cerrado.")
        if ok: self.reload()

    # ── render ────────────────────────────────────────────────────────────────
    def _render_detail(self, detail):
        self._detail = detail
        status = SHIPMENT_STATUS_ES.get(detail["status"], detail["status"])
        self._summary.setText(
            f"{detail['shipment_number']} · {status}\n"
            f"Origen: {detail.get('origin_location') or '—'} · "
            f"{detail['container_count']} contenedores · {detail['total_quantity']} unidades · "
            f"{detail['net_weight']} kg")
        self._tree.load_rows([[
            f"{'— ' * item['depth']}{item['container_code']}", item["type_name"],
            NODE_STATUS_ES.get(item["status"], item["status"]), item["net_weight"],
        ] for item in detail["nodes"]], row_ids=[item["id"] for item in detail["nodes"]])
        node_codes = {item["id"]: item["container_code"] for item in detail["nodes"]}
        self._contents.load_rows([[
            item.get("product_name", "Producto"), node_codes.get(item["node_id"], "—"),
            item["quantity"], item["net_weight"], item["lot_number"],
        ] for item in detail["contents"]], row_ids=[item["id"] for item in detail["contents"]])
        self._differences.load_rows([[
            item.get("product_name", "Producto"), item["expected"], item["loaded"],
            item["variance"], "Bloqueada" if item["blocking"] else "Pendiente",
        ] for item in detail["differences"]], row_ids=[item["source_line_id"] for item in detail["differences"]])
        pending = detail["pending_authorizations"]
        self._authorization.setText(
            f"{len(pending)} autorización(es) requeridas: " + "; ".join(item["reason"] for item in pending)
            if pending else "Sin autorizaciones pendientes")
        can_load = detail.get("can_load", False)
        for widget in (self._container_ref, self._inside, self._attach, self._load):
            widget.setEnabled(can_load and self._can("origin_create"))
        self._register.setEnabled(self._can("origin_containers"))
        self._authorization_reason.setEnabled(bool(pending) and self._can("origin_override"))
        self._authorize.setEnabled(bool(pending) and self._can("origin_override"))
        self._mobile.setEnabled(can_load)
        can_seal = detail["can_seal"] and can_load and self._can("origin_seal")
        self._seal_code.setEnabled(can_seal)
        self._seal.setEnabled(can_seal)
        self._dispatch.setEnabled(detail["can_dispatch"] and can_load
                                  and self._can("origin_dispatch"))
        self._transit.setEnabled(detail.get("can_mark_transit", False)
                                 and self._can("origin_dispatch"))
        self._arrive.setEnabled(detail.get("can_arrive", False) and self._can("origin_receive"))
        self._count.setEnabled(detail.get("can_count", False) and self._can("origin_receive"))
        self._receive.setEnabled(detail.get("can_receive", False)
                                 and self._can("origin_receive") and self._can("receipt_complete"))
        self._render_arrival()

    def _render_arrival(self):
        self._arrival = []
        if self._detail and self._detail.get("status") in ("ARRIVED", "RECEIVING", "CLOSED"):
            self._arrival = self._presenter.origin_arrival_lines(self._detail["id"])
        self._arrival_table.load_rows([[
            line["product_name"], line["container_code"],
            f"{line['declared_quantity']} {line.get('purchase_unit') or ''}".strip(),
            line["received_quantity"] if line["counted"] else "Por contar",
            line["accepted_quantity"] if line["counted"] else "—",
            line["received_net_weight"] if line["counted"] else "—",
        ] for line in self._arrival], row_ids=[line["content_id"] for line in self._arrival])

    def _feedback(self, ok, message):
        self._notice.setProperty("state", "success" if ok else "error")
        self._notice.style().unpolish(self._notice)
        self._notice.style().polish(self._notice)
        self._notice.setText(message)

    @staticmethod
    def _type_label(value):
        return {"PURCHASE_ORDER": "Orden de compra", "DIRECT_PURCHASE": "Compra directa",
                "PURCHASE_REQUISITION": "Solicitud aprobada"}.get(value, value)
