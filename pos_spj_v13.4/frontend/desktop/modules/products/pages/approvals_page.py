"""Aprobaciones técnicas — versiones de receta, rendimiento, despiece y combo
que esperan revisión, aprobación o activación, de TODOS los productos (§22, §39).

No repite el expediente: el detalle de cada versión se sigue editando desde el
producto («Más acciones»); aquí está la bandeja de quien firma. Las acciones
llaman a los mismos casos de uso, que revalidan permiso y segregación (quien
creó una versión no puede aprobarla).
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
from frontend.desktop.components.buttons import (
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.components.page_viewport import PageViewport
from frontend.desktop.themes.tokens import Spacing

KIND_ES = {"RECIPE": "Receta", "YIELD": "Rendimiento", "CUTTING": "Despiece",
           "BUNDLE": "Combo"}
STATUS_ES = {"DRAFT": "Borrador", "UNDER_REVIEW": "En revisión", "APPROVED": "Aprobada"}

#: tipo → nombre del método del presenter por acción
_ACTIONS = {
    "RECIPE": ("submit_recipe_version", "approve_recipe_version", "activate_recipe_version"),
    "YIELD": ("submit_yield_version", "approve_yield_version", "activate_yield_version"),
    "CUTTING": ("submit_cutting_version", "approve_cutting_version",
                "activate_cutting_version"),
    "BUNDLE": ("submit_bundle_version", "approve_bundle_version", "activate_bundle_version"),
}


class ApprovalsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("productApprovalsPage")
        self._presenter = presenter
        self._approvals = getattr(presenter, "approvals", None)
        self._rows: list[dict] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.viewport = PageViewport(self)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)
        layout.addWidget(PageHeader(
            title="Aprobaciones técnicas",
            subtitle="Recetas, rendimientos, despieces y combos que esperan revisión, "
                     "aprobación o activación.",
            icon=getattr(Icons, "APPROVAL", None), compact=True))

        filters = QHBoxLayout()
        self.kind = QComboBox()
        self.kind.setAccessibleName("Tipo")
        self.kind.addItem("Todos los tipos", "")
        for key, label in KIND_ES.items():
            self.kind.addItem(label, key)
        self.status = QComboBox()
        self.status.setAccessibleName("Estado")
        self.status.addItem("Todo lo pendiente", "")
        for key, label in STATUS_ES.items():
            self.status.addItem(label, key)
        self.kind.currentIndexChanged.connect(lambda _i: self.refresh())
        self.status.currentIndexChanged.connect(lambda _i: self.refresh())
        filters.addWidget(self.kind)
        filters.addWidget(self.status)
        filters.addStretch(1)
        self.btn_submit = create_secondary_button(self, "Enviar a revisión")
        self.btn_approve = create_primary_button(self, "Aprobar")
        self.btn_activate = create_secondary_button(self, "Activar")
        for button, index in ((self.btn_submit, 0), (self.btn_approve, 1),
                              (self.btn_activate, 2)):
            button.clicked.connect(lambda _c=False, i=index: self._act(i))
            filters.addWidget(button)
        layout.addLayout(filters)

        self.table = StandardTable(columns=[
            ColumnSpec("Tipo", "text"), ColumnSpec("Producto", "text"),
            ColumnSpec("Nombre", "text"), ColumnSpec("Versión", "numeric"),
            ColumnSpec("Estado", "status"), ColumnSpec("Creada por", "text"),
            ColumnSpec("Fecha", "date")])
        self.table.itemSelectionChanged.connect(self._update_buttons)
        layout.addWidget(self.table, 1)

        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setProperty("role", "banner")
        self.message.hide()
        layout.addWidget(self.message)
        self.viewport.set_page(body)
        outer.addWidget(self.viewport)
        self.refresh()

    def refresh(self) -> None:
        self._rows = (self._approvals.pending(kind=self.kind.currentData() or None,
                                              status=self.status.currentData() or None)
                      if self._approvals is not None else [])
        self.table.load_rows(
            [[KIND_ES.get(r["kind"], r["kind"]),
              f"{r['product_code'] or ''} · {r['product_name'] or ''}".strip(" ·"),
              r["name"] or "", str(r["version_number"] or ""),
              STATUS_ES.get(r["status"], r["status"]), r["created_by_name"] or "",
              (r["created_at"] or "")[:16].replace("T", " ")] for r in self._rows],
            row_ids=[r["version_id"] for r in self._rows])
        self._update_buttons()

    def _selected(self) -> dict | None:
        version_id = self.table.selected_row_id()
        return next((r for r in self._rows if r["version_id"] == version_id), None)

    def _update_buttons(self) -> None:
        row = self._selected()
        status = row["status"] if row else None
        self.btn_submit.setEnabled(status == "DRAFT")
        self.btn_approve.setEnabled(status == "UNDER_REVIEW")
        self.btn_activate.setEnabled(status == "APPROVED")

    def _act(self, index: int) -> None:
        row = self._selected()
        if row is None:
            QMessageBox.information(self, "Aprobaciones técnicas", "Selecciona una versión.")
            return
        method = getattr(self._presenter, _ACTIONS[row["kind"]][index], None)
        if method is None:
            self._show(False, "Esta acción no está disponible.")
            return
        ok, message = method(row["version_id"])
        done = ("Enviada a revisión.", "Aprobada.", "Activada.")[index]
        self._show(ok, done if ok else (message or "No se pudo completar."))
        if ok:
            self.refresh()

    def _show(self, ok: bool, text: str) -> None:
        self.message.setText(text)
        self.message.setProperty("state", "success" if ok else "error")
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)
        self.message.setVisible(bool(text))
