"""Calidad de datos — qué le falta a cada producto para estar completo (§35, §42).

UI only: indicadores del resumen, filtro por tipo de pendiente y la lista de
productos con su puntaje. «Abrir ficha» lleva a la ficha del producto para
corregirlo. Las reglas viven en el backend (las mismas de las alertas §35).
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components import (
    KPIBar,
    KPIDTO,
    ColumnSpec,
    PageHeader,
    StandardTable,
)
from frontend.desktop.components.buttons import create_secondary_button
from frontend.desktop.components.icons import Icons
from frontend.desktop.components.page_viewport import PageViewport
from frontend.desktop.themes.tokens import Spacing

STATUS_ES = {"DRAFT": "Borrador", "UNDER_REVIEW": "En revisión", "ACTIVE": "Activo",
             "INACTIVE": "Inactivo", "BLOCKED": "Bloqueado", "DISCONTINUED": "Descontinuado"}


class DataQualityPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("productDataQualityPage")
        self._presenter = presenter
        self._quality = getattr(presenter, "data_quality", None)
        self._rows: list[dict] = []
        self._data_changed = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.viewport = PageViewport(self)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)
        layout.addWidget(PageHeader(
            title="Calidad de datos",
            subtitle="Productos con datos faltantes o inconsistentes y su puntaje (0-100).",
            icon=getattr(Icons, "QUALITY", None), compact=True))
        self.kpis = KPIBar()
        layout.addWidget(self.kpis)

        bar = QHBoxLayout()
        self.issue = QComboBox()
        self.issue.setAccessibleName("Pendiente")
        self.issue.currentIndexChanged.connect(lambda _i: self._fill())
        bar.addWidget(QLabel("Mostrar"))
        bar.addWidget(self.issue, 1)
        self.btn_open = create_secondary_button(self, "Corregir",
                                                "Abre el dato faltante del producto seleccionado")
        menu = QMenu(self.btn_open)
        for label, opener in (("Ficha del producto…", self._open_form),
                              ("Clasificación cárnica y peso variable…", self._open_meat),
                              ("Calidad, vida útil y logística…", self._open_profiles),
                              ("Imágenes…", self._open_images)):
            menu.addAction(label).triggered.connect(lambda _c=False, f=opener: self._fix(f))
        self.btn_open.setMenu(menu)
        bar.addWidget(self.btn_open)
        layout.addLayout(bar)

        self.table = StandardTable(columns=[
            ColumnSpec("Código", "text", min_width=90, preferred_width=110),
            ColumnSpec("Producto", "text", min_width=120, preferred_width=160),
            ColumnSpec("Estado", "status", min_width=80, preferred_width=90),
            ColumnSpec("Puntaje", "numeric", min_width=70, preferred_width=80),
            ColumnSpec("Pendientes", "text", min_width=240, preferred_width=420,
                       stretch=True)])
        layout.addWidget(self.table, 1)
        self.empty = QLabel("")
        self.empty.setProperty("role", "muted")
        layout.addWidget(self.empty)
        self.viewport.set_page(body)
        outer.addWidget(self.viewport)
        self.refresh()

    def set_data_changed_signal(self, signal) -> None:
        self._data_changed = signal
        signal.connect(self.refresh)

    def refresh(self) -> None:
        if self._quality is None:
            self.empty.setText("La calidad de datos no está disponible.")
            return
        self._rows = self._quality.report()
        summary = self._quality.summary()
        self.kpis.set_cards([
            KPIDTO(key="dq_products", title="Productos", value=str(summary["products"])),
            KPIDTO(key="dq_issues", title="Con pendientes", value=str(summary["with_issues"]),
                   variant="warning" if summary["with_issues"] else "success"),
            KPIDTO(key="dq_score", title="Puntaje promedio",
                   value=f"{summary['average_score']}",
                   variant="success" if summary["average_score"] >= 80 else "warning"),
        ])
        current = self.issue.currentData()
        self.issue.blockSignals(True)
        self.issue.clear()
        self.issue.addItem("Todos los pendientes", "")
        labels = {}
        for row in self._rows:
            labels.update(zip(row["issues"], row["issue_labels"]))
        for code, count in sorted(summary["by_issue"].items(), key=lambda kv: -kv[1]):
            self.issue.addItem(f"{labels.get(code, code)} ({count})", code)
        self.issue.setCurrentIndex(max(0, self.issue.findData(current or "")))
        self.issue.blockSignals(False)
        self._fill()

    def _fill(self) -> None:
        code = self.issue.currentData()
        rows = [r for r in self._rows if not code or code in r["issues"]]
        self.table.load_rows(
            [[r["code"] or "", r["name"] or "",
              STATUS_ES.get(r["lifecycle_status"], r["lifecycle_status"] or ""),
              str(r["score"]), "; ".join(r["issue_labels"])] for r in rows],
            row_ids=[r["product_id"] for r in rows])
        self.empty.setText("" if rows else "Sin pendientes: el maestro está completo.")

    def _fix(self, opener) -> None:
        product_id = self.table.selected_row_id()
        if not product_id:
            self.empty.setText("Selecciona un producto de la lista.")
            return
        row = next((r for r in self._rows if r["product_id"] == product_id), {})
        opener(product_id, row.get("name") or "Producto")
        if self._data_changed is not None:
            self._data_changed.emit()
        else:
            self.refresh()

    def _open_form(self, product_id: str, _name: str) -> None:
        from frontend.desktop.modules.products.dialogs.product_form_dialog import (
            ProductFormDialog,
        )
        ProductFormDialog(self._presenter, product_id=product_id, parent=self).exec_()

    def _open_meat(self, product_id: str, name: str) -> None:
        from frontend.desktop.modules.products.dialogs.meat_product_dialog import (
            MeatProductDialog,
        )
        MeatProductDialog(self._presenter.meat, product_id=product_id, product_name=name,
                          parent=self).exec_()

    def _open_profiles(self, product_id: str, name: str) -> None:
        from frontend.desktop.modules.products.dialogs.profiles_dialog import ProfilesDialog
        ProfilesDialog(self._presenter.codes_profiles, product_id=product_id,
                       product_name=name, parent=self).exec_()

    def _open_images(self, product_id: str, name: str) -> None:
        from frontend.desktop.modules.products.dialogs.image_gallery_dialog import (
            ImageGalleryDialog,
        )
        ImageGalleryDialog(self._presenter, product_id=product_id, product_name=name,
                           parent=self).exec_()
