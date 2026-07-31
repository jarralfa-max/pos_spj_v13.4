"""Sucursales y canales (§10) — habilitación por sucursal + surtido por canal.

UI only: selecciona un producto (búsqueda), habilita/deshabilita por sucursal y lo
incluye/excluye de surtidos por canal. Toda mutación pasa por el presenter →
use cases canónicos (`branch_product` / `assortments`). Sin SQL ni lógica aquí.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components import (
    ColumnSpec,
    PageHeader,
    SearchInput,
    StandardTable,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class BranchChannelPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("branchChannelPage")
        self._presenter = presenter
        self._product_id: str | None = None
        self._can_branch = bool(getattr(presenter, "can_manage_branch_assignment", False))
        self._can_assort = bool(getattr(presenter, "can_manage_assortment", False))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)
        layout.addWidget(PageHeader(
            title="Sucursales y canales",
            subtitle="Habilita productos por sucursal y arma los surtidos por canal.",
            icon=getattr(Icons, "CATALOG", None), compact=True))

        # ── selección de producto ────────────────────────────────────────────
        self.search = SearchInput(placeholder="Buscar producto por nombre o código…")
        self.search.textChanged.connect(self._on_search)
        layout.addWidget(self.search)
        self.products = StandardTable(columns=[
            ColumnSpec("Código", "code"), ColumnSpec("Nombre", "name")])
        layout.addWidget(self.products, 1)
        row = QHBoxLayout()
        self.btn_load = QPushButton("Ver asignaciones del producto")
        self.btn_load.clicked.connect(self._load_selected_product)
        row.addWidget(self.btn_load)
        self._selected_label = QLabel("Ningún producto seleccionado")
        row.addWidget(self._selected_label, 1)
        layout.addLayout(row)

        # ── sucursales ───────────────────────────────────────────────────────
        layout.addWidget(QLabel("Sucursales"))
        self.branches = StandardTable(columns=[
            ColumnSpec("Sucursal", "branch"), ColumnSpec("Estado", "estado")])
        layout.addWidget(self.branches, 1)
        self.btn_toggle_branch = QPushButton("Habilitar/Deshabilitar sucursal")
        self.btn_toggle_branch.setEnabled(self._can_branch)
        self.btn_toggle_branch.clicked.connect(self._toggle_branch)
        layout.addWidget(self.btn_toggle_branch)

        # ── canales / surtidos ───────────────────────────────────────────────
        layout.addWidget(QLabel("Surtidos por canal"))
        self.assortments = StandardTable(columns=[
            ColumnSpec("Surtido", "name"), ColumnSpec("Canal", "channel"),
            ColumnSpec("Incluido", "incluido")])
        layout.addWidget(self.assortments, 1)
        arow = QHBoxLayout()
        self.btn_toggle_assort = QPushButton("Incluir/Quitar del surtido")
        self.btn_toggle_assort.setEnabled(self._can_assort)
        self.btn_toggle_assort.clicked.connect(self._toggle_assortment)
        self.btn_new_assort = QPushButton("Nuevo surtido")
        self.btn_new_assort.setEnabled(self._can_assort)
        self.btn_new_assort.clicked.connect(self._new_assortment)
        arow.addWidget(self.btn_toggle_assort)
        arow.addWidget(self.btn_new_assort)
        arow.addStretch(1)
        layout.addLayout(arow)

        self.refresh()

    # ── búsqueda / selección ─────────────────────────────────────────────────
    def _on_search(self, text) -> None:
        rows = self._presenter.search_products_for_assignment(query=text or None)
        self.products.load_rows([[r["code"], r["name"]] for r in rows],
                                row_ids=[r["id"] for r in rows])

    def _load_selected_product(self) -> None:
        pid = self.products.selected_row_id()
        if not pid:
            QMessageBox.information(self, "Selecciona un producto",
                                   "Elige un producto de la lista primero.")
            return
        self._product_id = pid
        self._selected_label.setText(f"Producto: {pid}")
        self._refresh_assignments()

    def refresh(self) -> None:
        self._on_search(self.search.text() or "")
        if self._product_id:
            self._refresh_assignments()

    def _refresh_assignments(self) -> None:
        if not self._product_id:
            return
        branches = self._presenter.branch_assignments(self._product_id)
        self.branches.load_rows(
            [[b["branch_name"], "Habilitado" if b["enabled"] else "No"] for b in branches],
            row_ids=[b["branch_id"] for b in branches])
        self._branch_state = {b["branch_id"]: b["enabled"] for b in branches}
        assort = self._presenter.assortments(self._product_id)
        self.assortments.load_rows(
            [[a["name"], a["channel"], "Sí" if a["contains"] else "No"] for a in assort],
            row_ids=[a["id"] for a in assort])
        self._assort_state = {a["id"]: a["contains"] for a in assort}

    # ── mutaciones (delegan al presenter) ────────────────────────────────────
    def _toggle_branch(self) -> None:
        if not self._require_product():
            return
        branch_id = self.branches.selected_row_id()
        if not branch_id:
            return
        enabled = not bool(getattr(self, "_branch_state", {}).get(branch_id, False))
        ok, msg = self._presenter.set_branch_enabled(
            product_id=self._product_id, branch_id=branch_id, enabled=enabled)
        if not ok:
            QMessageBox.warning(self, "Sucursal", msg)
        self._refresh_assignments()

    def _toggle_assortment(self) -> None:
        if not self._require_product():
            return
        assortment_id = self.assortments.selected_row_id()
        if not assortment_id:
            return
        enabled = not bool(getattr(self, "_assort_state", {}).get(assortment_id, False))
        ok, msg = self._presenter.set_assortment_product(
            assortment_id=assortment_id, product_id=self._product_id, enabled=enabled)
        if not ok:
            QMessageBox.warning(self, "Surtido", msg)
        self._refresh_assignments()

    def _new_assortment(self) -> None:
        channels = self._presenter.list_channels()
        if not channels:
            return
        name, ok = QInputDialog.getText(self, "Nuevo surtido", "Nombre del surtido:")
        if not ok or not name.strip():
            return
        labels = [c["label"] for c in channels]
        label, ok = QInputDialog.getItem(self, "Canal", "Canal:", labels, 0, False)
        if not ok:
            return
        channel = next(c["value"] for c in channels if c["label"] == label)
        ok2, msg = self._presenter.create_assortment(name=name.strip(), channel=channel)
        if not ok2:
            QMessageBox.warning(self, "Surtido", msg)
        self._refresh_assignments()

    def _require_product(self) -> bool:
        if not self._product_id:
            QMessageBox.information(self, "Selecciona un producto",
                                   "Carga primero las asignaciones de un producto.")
            return False
        return True
