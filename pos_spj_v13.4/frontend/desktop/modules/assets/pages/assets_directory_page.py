"""AssetsDirectoryPage (ASSET-18, route ``assets.directory``) — listado y
búsqueda de activos de la sucursal activa.

Mirrors ``frontend/desktop/modules/customers_crm/pages/_directory_base.py``'s
search+status+StandardTable shape, built directly here (not as a shared base
class) since Activos has one directory page today, unlike CRM's four
simultaneous ones — extracting a base class before a second consumer exists
would be premature.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget

from backend.domain.assets.enums import AssetStatus
from frontend.desktop.components import (
    ColumnSpec,
    PageHeader,
    SearchableComboBox,
    SearchInput,
    SectionCard,
    StandardTable,
    ViewState,
    create_state_widget,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing

_STATUS_LABELS = {
    AssetStatus.DRAFT.value: "Borrador", AssetStatus.AVAILABLE.value: "Disponible",
    AssetStatus.ASSIGNED.value: "Asignado", AssetStatus.IN_USE.value: "En uso",
    AssetStatus.IN_MAINTENANCE.value: "En mantenimiento",
    AssetStatus.OUT_OF_SERVICE.value: "Fuera de servicio", AssetStatus.LOANED.value: "Prestado",
    AssetStatus.MISSING.value: "No localizado",
    AssetStatus.DISPOSAL_PENDING.value: "Baja pendiente", AssetStatus.DISPOSED.value: "Dado de baja",
    AssetStatus.SOLD.value: "Vendido", AssetStatus.DONATED.value: "Donado",
    AssetStatus.STOLEN.value: "Robado", AssetStatus.LOST.value: "Perdido",
}


class AssetsDirectoryPage(QWidget):
    entity_selected = pyqtSignal(str)

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("assetsDirectoryPage")
        self._presenter = presenter
        self._loaded = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(Spacing.MD)
        root.addWidget(PageHeader(
            self, title="Directorio", subtitle="Listado y búsqueda de activos.",
            icon=Icons.ASSETS, compact=True))

        self._status = QLabel("", self)
        self._status.setObjectName("assetsDirectoryStatus")
        self._status.setProperty("state", "ERROR")
        self._status.setWordWrap(True)
        self._status.hide()
        root.addWidget(self._status)

        card = SectionCard(self, title="Directorio de activos")
        filter_row = QHBoxLayout()
        filter_row.setSpacing(Spacing.SM)
        self._search = SearchInput(self, placeholder="Buscar por folio o nombre…")
        self._search.setAccessibleName("Buscar activos")
        self._search.search_changed.connect(lambda *_: self.reload())
        filter_row.addWidget(self._search, stretch=1)
        self._status_filter = SearchableComboBox(self, placeholder="Todos los estados")
        self._status_filter.set_options([("", "Todos"), *_STATUS_LABELS.items()])
        self._status_filter.selection_changed.connect(lambda *_: self.reload())
        filter_row.addWidget(self._status_filter)
        card.body().addLayout(filter_row)

        self._stack = QStackedWidget(self)
        self._table = StandardTable(
            [ColumnSpec("Folio"), ColumnSpec("Nombre"), ColumnSpec("Categoría"),
             ColumnSpec("Ubicación"), ColumnSpec("Estado", "status")], self)
        self._table.setAccessibleName("Listado de activos")
        self._table.doubleClicked.connect(self._on_row_activated)
        self._empty = create_state_widget(
            ViewState.EMPTY, self, message="No se encontraron activos")
        self._stack.addWidget(self._table)
        self._stack.addWidget(self._empty)
        card.body().addWidget(self._stack)
        root.addWidget(card, stretch=1)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        try:
            assets = self._presenter.directory(
                search=self._search.text().strip(),
                status=self._status_filter.current_id() or None)
            rows = [self._row(asset) for asset in assets]
            row_ids = [asset.id for asset in assets]
            self._table.load_rows(rows, row_ids=row_ids)
            self._stack.setCurrentWidget(self._table if rows else self._empty)
            self._loaded = True
            self._status.hide()
        except Exception as exc:  # a page must always show *something*
            self._status.setText(f"No fue posible cargar el directorio: {exc}")
            self._status.show()

    def _on_row_activated(self, _index) -> None:
        row_id = self._table.selected_row_id()
        if row_id:
            self.entity_selected.emit(row_id)

    @staticmethod
    def _row(asset) -> list[str]:
        return [
            asset.asset_number, asset.name, asset.category_name or "—",
            asset.location_name or "—",
            _STATUS_LABELS.get(asset.status.value, asset.status.value),
        ]
