"""Read-only Logistics references visible from Procurement."""

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable, ViewState, create_state_widget
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class LogisticsRelatedPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._loaded = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.addWidget(PageHeader(title="Embarques relacionados",
                                    subtitle="Referencia logística; Compras no recibe inventario.",
                                    icon=Icons.PURCHASES, compact=True))
        self._table = StandardTable([
            ColumnSpec("Embarque"), ColumnSpec("Origen"), ColumnSpec("Estado", "status"),
            ColumnSpec("Inicio", "date"), ColumnSpec("Despacho", "date"),
        ], self)
        self._empty = create_state_widget(ViewState.EMPTY, self,
                                          message="No hay embarques para el contexto activo.")
        layout.addWidget(self._table, stretch=1)
        layout.addWidget(self._empty, stretch=1)

    def ensure_loaded(self):
        if not self._loaded:
            self.reload()

    def reload(self):
        try:
            rows = self._presenter.related_shipments()
            missing_context = False
        except PermissionError:
            rows = []
            missing_context = True
        self._table.load_rows([
            [row["shipment_number"], row["origin_type"], row["status"],
             row["started_at"] or "—", row["dispatched_at"] or "—"] for row in rows
        ], row_ids=[row["id"] for row in rows])
        self._table.setVisible(bool(rows))
        self._empty.setVisible(not rows)
        if missing_context:
            self._empty.setProperty("state", ViewState.NO_PERMISSION)
            self._empty.setAccessibleName(
                "Selecciona un almacén antes de consultar embarques relacionados.")
        self._loaded = True
