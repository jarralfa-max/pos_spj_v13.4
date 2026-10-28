"""Catálogo externo — traer datos de producto de fuentes externas, revisarlos e
importarlos (§15, PROD-22).

UI only. Flujo: buscar (texto o código de barras) → los resultados quedan «en
revisión» (si el código ya existe en el maestro, marcados como coincidencia) →
aprobar o rechazar → importar como producto nuevo (con tipo, unidad y categoría,
que la fuente externa no conoce). Nada entra al maestro sin revisión.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components import ColumnSpec, PageHeader, SearchInput, StandardTable
from frontend.desktop.components.buttons import (
    create_danger_button,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.dialogs import MessageDialog, StandardDialog
from frontend.desktop.components.icons import Icons
from frontend.desktop.components.page_viewport import PageViewport
from frontend.desktop.modules.products.external_catalog_presenter import STATUS_ES
from frontend.desktop.modules.products.view_models import PRODUCT_TYPE_ES
from frontend.desktop.themes.tokens import Spacing


class ExternalCatalogPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("externalCatalogPage")
        self._presenter = presenter
        self._ext = getattr(presenter, "external", None)
        self._rows: list[dict] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.viewport = PageViewport(self)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)
        layout.addWidget(PageHeader(
            title="Catálogo externo",
            subtitle="Busca un producto en una fuente externa, revísalo e impórtalo al maestro.",
            icon=getattr(Icons, "EXTERNAL", None), compact=True))

        search_bar = QHBoxLayout()
        self.source = QComboBox()
        self.source.setAccessibleName("Fuente")
        self.query = SearchInput(placeholder="Nombre o código de barras…")
        self.btn_search = create_primary_button(self, "Buscar")
        self.btn_search.clicked.connect(self._search)
        search_bar.addWidget(self.source)
        search_bar.addWidget(self.query, 1)
        search_bar.addWidget(self.btn_search)
        layout.addLayout(search_bar)

        actions = QHBoxLayout()
        self.status = QComboBox()
        self.status.setAccessibleName("Estado")
        self.status.addItem("Todos los estados", "")
        for key, label in STATUS_ES.items():
            self.status.addItem(label, key)
        self.status.currentIndexChanged.connect(lambda _i: self.refresh())
        actions.addWidget(self.status)
        actions.addStretch(1)
        self.btn_approve = create_secondary_button(self, "Aprobar")
        self.btn_reject = create_danger_button(self, "Rechazar")
        self.btn_import = create_primary_button(self, "Importar…")
        for button, slot in ((self.btn_approve, self._approve),
                             (self.btn_reject, self._reject),
                             (self.btn_import, self._import)):
            button.clicked.connect(slot)
            actions.addWidget(button)
        layout.addLayout(actions)

        self.table = StandardTable(columns=[
            ColumnSpec("Nombre", "text"), ColumnSpec("Marca", "text"),
            ColumnSpec("Código de barras", "text"), ColumnSpec("Contenido", "text"),
            ColumnSpec("Estado", "status"), ColumnSpec("Coincide con", "text"),
            ColumnSpec("Calidad", "numeric")])
        self.table.itemSelectionChanged.connect(self._update_buttons)
        layout.addWidget(self.table, 1)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setProperty("role", "banner")
        self.message.hide()
        layout.addWidget(self.message)
        self.viewport.set_page(body)
        outer.addWidget(self.viewport)

        if self._ext is not None:
            for s in self._ext.sources():
                self.source.addItem(s["name"], s["id"])
        can_search = self._ext is not None and self._ext.can_search and self.source.count()
        for widget in (self.source, self.query, self.btn_search):
            widget.setEnabled(bool(can_search))
        if self._ext is not None and not self.source.count():
            self._show(False, "No hay fuentes externas configuradas.")
        self.refresh()

    # ── datos ─────────────────────────────────────────────────────────────
    def refresh(self) -> None:
        self._rows = (self._ext.records(self.status.currentData() or None)
                      if self._ext is not None else [])
        self.table.load_rows(
            [[r["name"] or "", r["brand"] or "", r["barcode"] or "",
              " ".join(x for x in (r["net_weight"], r["unit"]) if x),
              STATUS_ES.get(r["status"], r["status"]), r["matched_label"],
              str(r["score"])] for r in self._rows],
            row_ids=[r["id"] for r in self._rows])
        self._update_buttons()

    def _selected(self) -> dict | None:
        record_id = self.table.selected_row_id()
        return next((r for r in self._rows if r["id"] == record_id), None)

    def _update_buttons(self) -> None:
        row = self._selected()
        status = row["status"] if row else None
        ext = self._ext
        reviewable = status in ("PENDING_REVIEW", "MATCHED")
        self.btn_approve.setEnabled(bool(ext and ext.can_approve and reviewable))
        self.btn_reject.setEnabled(bool(ext and ext.can_review and reviewable))
        self.btn_import.setEnabled(bool(ext and ext.can_import and status == "APPROVED"))

    def _show(self, ok: bool, text: str) -> None:
        self.message.setText(text)
        self.message.setProperty("state", "success" if ok else "error")
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)
        self.message.setVisible(bool(text))

    # ── acciones ──────────────────────────────────────────────────────────
    def _search(self) -> None:
        text = self.query.text().strip()
        if len(text) < 3:
            self._show(False, "Escribe al menos 3 caracteres o un código de barras.")
            return
        self._show(True, "Buscando…")
        ok, message = self._ext.search(source_id=self.source.currentData(), query=text)
        self._show(ok, message)
        self.refresh()

    def _need_selection(self) -> dict | None:
        row = self._selected()
        if row is None:
            MessageDialog.information(self, "Catálogo externo", "Selecciona un registro.")
        return row

    def _approve(self) -> None:
        row = self._need_selection()
        if row:
            ok, message = self._ext.approve(row["id"])
            self._show(ok, "Registro aprobado; ya se puede importar." if ok else message)
            self.refresh()

    def _reject(self) -> None:
        row = self._need_selection()
        if row:
            ok, message = self._ext.reject(row["id"])
            self._show(ok, "Registro rechazado." if ok else message)
            self.refresh()

    def _import(self) -> None:
        row = self._need_selection()
        if not row:
            return
        dialog = ImportExternalDialog(self._presenter, record=row, parent=self)
        if not dialog.exec_():
            return
        ok, message = self._ext.import_record(record_id=row["id"], **dialog.values())
        self._show(ok, "Producto importado al maestro (nace en borrador)." if ok else message)
        self.refresh()


class ImportExternalDialog(StandardDialog):
    """Lo que la fuente externa no sabe: tipo, unidad base y categoría."""

    def __init__(self, presenter, *, record: dict, parent=None) -> None:
        super().__init__(parent, title=f"Importar «{record.get('name') or ''}»")
        form = QFormLayout()
        self.product_type = QComboBox()
        for code, label in sorted(PRODUCT_TYPE_ES.items(), key=lambda kv: kv[1]):
            self.product_type.addItem(label, code)
        self.product_type.setCurrentIndex(max(0, self.product_type.findData("RESALE_PRODUCT")))
        self.unit = QComboBox()
        for u in presenter.list_units():
            self.unit.addItem(f"{u['code']} — {u['name']}", u["id"])
        self.category = QComboBox()
        self.category.addItem("(Sin categoría)", "")
        for c in presenter.list_categories():
            self.category.addItem(c["label"], c["id"])
        form.addRow("Tipo *", self.product_type)
        form.addRow("Unidad base *", self.unit)
        form.addRow("Categoría", self.category)
        self.content_layout().addLayout(form)
        self.error = QLabel("")
        self.error.setWordWrap(True)
        self.content_layout().addWidget(self.error)
        box = self.add_button_box(ok_text="Importar", on_accept=self._accept)
        box.button(QDialogButtonBox.Ok).setText("Importar")

    def values(self) -> dict:
        return {"product_type": self.product_type.currentData(),
                "base_unit_id": self.unit.currentData(),
                "category_id": self.category.currentData() or None}

    def _accept(self) -> None:
        if not self.unit.currentData():
            self.error.setText("La unidad base es obligatoria.")
            return
        self.accept()
