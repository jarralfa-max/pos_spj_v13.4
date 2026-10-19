"""Canonical responsive Transfers page shell using only SPJ Design System."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QLabel, QMessageBox, QVBoxLayout, QWidget

from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.cards import SectionCard
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.search_input import SearchInput
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.themes.tokens import Spacing


class TransferWorkspacePage(QWidget):
    page_id = ""
    title = "Transferencias"
    subtitle = "Operación logística interna"
    action_text = "Nueva solicitud"
    #: Acciones del ciclo sobre la fila elegida: (texto, nombre del manejador
    #: `_do_<nombre>`). Integración Logística 32cfbf.
    cycle_actions: tuple[tuple[str, str], ...] = ()

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._loaded = False
        self.setObjectName("transfersPage")
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.LG)
        root.setSpacing(Spacing.MD)
        self.action_button = create_primary_button(self, self.action_text)
        self.action_button.setVisible(bool(self.action_text))
        self.cycle_buttons = {}
        for texto, nombre in self.cycle_actions:
            boton = create_secondary_button(self, texto)
            boton.clicked.connect(getattr(self, f"_do_{nombre}"))
            boton.setEnabled(bool(getattr(presenter, "can_run", lambda _n: False)(
                {"receive": "receive", "dispatch": "dispatch", "prepare": "reserve",
                 "approve": "approve", "reject": "reject", "submit": "submit"}[nombre])))
            self.cycle_buttons[nombre] = boton
        acciones = ([self.action_button] if self.action_text else []) + list(
            self.cycle_buttons.values())
        root.addWidget(PageHeader(self, title=self.title, subtitle=self.subtitle,
                                  actions=acciones))
        self.search = SearchInput(self, placeholder="Buscar folio, origen o destino…")
        self.search.setAccessibleName(f"Buscar en {self.title}")
        self.search.search_changed.connect(self.reload)
        root.addWidget(self.search)
        card = SectionCard(self, title="Operaciones")
        self.table = StandardTable([
            ColumnSpec("Folio"), ColumnSpec("Origen"), ColumnSpec("Destino"),
            ColumnSpec("Estado", "status"), ColumnSpec("Actualización", "date"),
        ], card)
        self.table.setAccessibleName(f"Listado de {self.title}")
        self.table.setFocusPolicy(Qt.StrongFocus)
        card.add(self.table)
        self.empty_label = QLabel("", card)
        self.empty_label.setObjectName("emptyStateMessage")
        self.empty_label.setWordWrap(True)
        card.add(self.empty_label)
        root.addWidget(card, stretch=1)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload("")

    def reload(self, search: str = "") -> None:
        model = self._presenter.load_page(self.page_id, search)
        rows = [[row.reference, row.origin, row.destination, row.status,
                 row.updated_at] for row in model.rows]
        self.table.load_rows(rows, row_ids=[row.entity_id for row in model.rows])
        self.empty_label.setText(model.empty_message if not rows else "")
        self.empty_label.setVisible(not rows)
        self._loaded = True

    # ── acciones del ciclo ──────────────────────────────────────────────────
    def _selected(self) -> str | None:
        tid = self.table.selected_row_id()
        if not tid:
            QMessageBox.information(self, self.title, "Selecciona una transferencia de la lista.")
        return tid

    def _report(self, result) -> None:
        ok, message, _data = result
        (QMessageBox.information if ok else QMessageBox.warning)(self, self.title, message)
        if ok:
            self.reload(self.search.text() if hasattr(self.search, "text") else "")

    def _do_submit(self) -> None:
        tid = self._selected()
        if tid:
            self._report(self._presenter.submit(tid))

    def _do_approve(self) -> None:
        tid = self._selected()
        if tid:
            self._report(self._presenter.approve(tid))

    def _do_reject(self) -> None:
        from frontend.desktop.modules.transfers.dialogs.cycle_dialogs import RejectTransferDialog
        tid = self._selected()
        if not tid:
            return
        detalle = self._presenter.detail(tid) or {"number": ""}
        dialogo = RejectTransferDialog(self, number=detalle["number"])
        if dialogo.exec_() == QDialog.Accepted:
            self._report(self._presenter.reject(tid, dialogo.reason.text().strip()))

    def _do_prepare(self) -> None:
        tid = self._selected()
        if tid:
            self._report(self._presenter.prepare(tid))

    def _do_dispatch(self) -> None:
        from frontend.desktop.modules.transfers.dialogs.cycle_dialogs import (
            DispatchTransferDialog,
        )
        tid = self._selected()
        if not tid:
            return
        detalle = self._presenter.detail(tid)
        if detalle is None:
            QMessageBox.warning(self, self.title, "No se pudo leer la transferencia.")
            return
        dialogo = DispatchTransferDialog(self, detail=detalle,
                                         verify=self._presenter.verify_verifier)
        if dialogo.exec_() == QDialog.Accepted:
            self._report(self._presenter.dispatch(
                tid, verifier_user_id=dialogo.verifier_user_id, seal=dialogo.seal.text().strip(),
                vehicle=dialogo.vehicle.text().strip(),
                temperature=dialogo.temperature.decimal_value()))

    def _do_receive(self) -> None:
        from frontend.desktop.modules.transfers.dialogs.cycle_dialogs import (
            ReceiveTransferDialog,
        )
        tid = self._selected()
        if not tid:
            return
        detalle = self._presenter.detail(tid) or {}
        pendientes = [e for e in detalle.get("shipments", ()) if e["pending_lines"]]
        if not pendientes:
            QMessageBox.information(self, self.title, "Esta transferencia no tiene nada pendiente "
                                                      "de recibir.")
            return
        envio = pendientes[0]
        dialogo = ReceiveTransferDialog(self, detail=detalle, shipment=envio)
        if dialogo.exec_() == QDialog.Accepted:
            self._report(self._presenter.receive(tid, envio["shipment_id"], dialogo.lines()))

