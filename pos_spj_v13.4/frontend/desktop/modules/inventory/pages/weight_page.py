"""Weight page (INV-25 / §18, §28-29) — catch-weight stock on hand + capture.

Lists variable-weight (catch-weight) balances for the branch — product,
warehouse, bucket, pieces, weight and reserved weight — and lets an
authorized user capture a new reading (scale or manual) that gets applied to
inventory (§28 "Capturar peso") or open the capture history (§28 "Ver
historial"). Both actions are gated by the session's resolved capabilities
(§17) — the backend re-validates independently regardless of what the UI
shows. All values come from the presenter; no SQL, no business logic.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec,
    PageHeader,
    StandardTable,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.inventory.dialogs import (
    CaptureWeightDialog,
    WeightHistoryDialog,
)
from frontend.desktop.themes.tokens import Spacing


class WeightPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryWeightPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Peso variable",
            subtitle="Existencias de productos de peso variable (piezas y peso "
                     "capturado).",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.capture_button = create_primary_button(text="Capturar peso")
        self.capture_button.clicked.connect(self._on_capture)
        actions.addWidget(self.capture_button)
        self.history_button = create_secondary_button(text="Ver historial")
        self.history_button.clicked.connect(self._on_history)
        actions.addWidget(self.history_button)
        layout.addLayout(actions)

        self._table = StandardTable(columns=[
            ColumnSpec("Producto", "text"),
            ColumnSpec("Almacén", "text"),
            ColumnSpec("Estado", "status"),
            ColumnSpec("Piezas", "numeric"),
            ColumnSpec("Peso", "numeric"),
            ColumnSpec("Peso reservado", "numeric"),
        ])
        layout.addWidget(self._table)

    def refresh(self) -> None:
        table = self._presenter.catch_weight()
        self._table.load_rows(table.rows, row_ids=table.row_ids)
        caps = self._presenter.capabilities()
        self.capture_button.setVisible(
            caps.weight_capture or caps.weight_manual_override)

    def _on_capture(self) -> None:
        dlg = CaptureWeightDialog(
            self, product_provider=self._presenter.product_options,
            location_options=self._presenter.location_options(),
            read_scale=self._presenter.read_scale)
        if dlg.exec_() != QDialog.Accepted:
            return
        product_id = dlg.product_id()
        if not product_id:
            QMessageBox.warning(self, "Peso variable", "Selecciona un producto de la lista.")
            return
        ok, message, _ = self._presenter.record_catch_weight(
            product_id=product_id, use_scale=dlg.use_scale(),
            pieces_delta=dlg.pieces_delta(), gross=dlg.gross(), tare=dlg.tare(),
            unit=dlg.unit(), authorizer_user_id=dlg.authorizer_user_id(),
            reason_note=dlg.note(), location_id=dlg.location_id())
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Peso variable", message)
        if ok:
            self.refresh()

    def _on_history(self) -> None:
        dlg = WeightHistoryDialog(self, table=self._presenter.weight_history())
        dlg.exec_()
