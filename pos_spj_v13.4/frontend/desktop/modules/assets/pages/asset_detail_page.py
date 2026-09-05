"""AssetDetailPage (ASSET-18, route ``assets.detail``) — read-only summary
of one activo.

§94 describes a full tabbed ``AssetSummaryHeader`` (Resumen/Información/
Ubicación/Custodia/Mantenimiento/Inspecciones/Costos/Documentos/Garantía/
Movimientos/Finanzas/Auditoría). This phase builds a single-panel read-only
summary using ``AssetDetailDTO`` (ASSET-14) instead — the tabbed experience
needs several QueryServices this pipeline hasn't built yet (inspections,
documents, warranty, financial projection) and would mean fabricating empty
tabs with nothing real to show, which is worse than one honest panel.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QFormLayout, QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import PageHeader, SectionCard, ViewState, create_state_widget
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class AssetDetailPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("assetDetailPage")
        self._presenter = presenter
        self._asset_id: str | None = None

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(Spacing.MD)

        self._header = PageHeader(
            self, title="Detalle de activo", subtitle="", icon=Icons.ASSETS, compact=True)
        self._root.addWidget(self._header)

        self._card = SectionCard(self, title="Información general")
        self._form = QFormLayout()
        self._form.setSpacing(Spacing.SM)
        self._labels: dict[str, QLabel] = {}
        for key, caption in (
            ("asset_number", "Folio"), ("category_name", "Categoría"),
            ("location_name", "Ubicación"), ("status", "Estado"),
            ("condition", "Condición"), ("criticality", "Criticidad"),
            ("manufacturer", "Fabricante"), ("model", "Modelo"),
            ("serial_number", "Número de serie"), ("custody", "Custodia"),
        ):
            value_label = QLabel("—", self)
            value_label.setWordWrap(True)
            self._labels[key] = value_label
            self._form.addRow(QLabel(f"{caption}:", self), value_label)
        self._card.body().addLayout(self._form)

        self._empty = create_state_widget(
            ViewState.EMPTY, self, message="Selecciona un activo del directorio")
        self._root.addWidget(self._empty)
        self._root.addWidget(self._card, stretch=1)
        self._card.hide()

    def show_asset(self, asset_id: str) -> None:
        self._asset_id = asset_id
        self.reload()

    def ensure_loaded(self) -> None:
        pass  # nothing to preload without a selected asset (§94 route enters via a row click)

    def reload(self) -> None:
        if not self._asset_id:
            self._card.hide()
            self._empty.show()
            return
        try:
            detail = self._presenter.detail(self._asset_id)
        except Exception:
            detail = None
        if detail is None:
            self._card.hide()
            self._empty.show()
            return
        self._empty.hide()
        self._card.show()
        self._header.set_subtitle(detail.asset.name)
        self._labels["asset_number"].setText(detail.asset.asset_number)
        self._labels["category_name"].setText(detail.asset.category_name or "—")
        self._labels["location_name"].setText(detail.asset.location_name or "—")
        self._labels["status"].setText(detail.asset.status.value)
        self._labels["condition"].setText(detail.asset.condition.value)
        self._labels["criticality"].setText(detail.asset.criticality.value)
        self._labels["manufacturer"].setText(detail.manufacturer or "—")
        self._labels["model"].setText(detail.model or "—")
        self._labels["serial_number"].setText(detail.serial_number or "—")
        self._labels["custody"].setText(
            "Con custodio activo" if detail.has_active_assignment else "Sin custodio activo")
