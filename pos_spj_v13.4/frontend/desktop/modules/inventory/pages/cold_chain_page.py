"""Cold chain page (INV-25 / §21) — open temperature excursions + operational
registro/resolución.

Lists open (unresolved) temperature excursions — warehouse, lot, temperature,
range, status and action taken — and lets an authorized user record a new
reading ("Registrar lectura") or resolve a selected excursion ("Resolver
excursión"), releasing or rejecting the lot the auto-block quarantined. Both
actions are gated by the session's resolved capabilities (§17) — the backend
re-validates every one independently. All values come from the presenter; no
SQL, no business logic.
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
    RecordTemperatureReadingDialog,
    ResolveExcursionDialog,
)
from frontend.desktop.themes.tokens import Spacing


class ColdChainPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryColdChainPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Cadena de frío",
            subtitle="Excursiones de temperatura abiertas y acción tomada.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.record_button = create_primary_button(text="Registrar lectura")
        self.record_button.clicked.connect(self._on_record)
        actions.addWidget(self.record_button)
        self.resolve_button = create_secondary_button(text="Resolver excursión")
        self.resolve_button.clicked.connect(self._on_resolve)
        actions.addWidget(self.resolve_button)
        layout.addLayout(actions)

        self._table = StandardTable(columns=[
            ColumnSpec("Almacén", "text"),
            ColumnSpec("Lote", "text"),
            ColumnSpec("Temperatura", "text"),
            ColumnSpec("Rango", "text"),
            ColumnSpec("Estado", "status"),
            ColumnSpec("Acción", "text"),
        ])
        layout.addWidget(self._table)

    def refresh(self) -> None:
        table = self._presenter.cold_chain_excursions()
        self._table.load_rows(table.rows, row_ids=table.row_ids)
        caps = self._presenter.capabilities()
        self.record_button.setVisible(caps.temperature_record)
        self.resolve_button.setVisible(caps.temperature_resolve)

    def _selected_excursion_id(self) -> str | None:
        eid = self._table.selected_row_id()
        if not eid:
            QMessageBox.information(
                self, "Cadena de frío", "Selecciona una excursión de la lista.")
            return None
        return eid

    def _on_record(self) -> None:
        dlg = RecordTemperatureReadingDialog(
            self, warehouse_options=self._presenter.warehouse_options(),
            product_provider=self._presenter.product_options,
            lots_provider=lambda pid: self._presenter.lots(product_id=pid))
        if dlg.exec_() != QDialog.Accepted:
            return
        sensor_id = dlg.sensor_id()
        if not sensor_id:
            QMessageBox.warning(self, "Cadena de frío", "Captura el identificador del sensor.")
            return
        temperature = dlg.temperature()
        min_temp, max_temp = dlg.min_temp(), dlg.max_temp()
        if temperature is None or min_temp is None or max_temp is None:
            QMessageBox.warning(self, "Cadena de frío", "Captura la temperatura y el rango.")
            return
        ok, message, _ = self._presenter.record_temperature_reading(
            sensor_id=sensor_id, warehouse_id=dlg.warehouse_id(), temperature=temperature,
            reading_point=dlg.reading_point(), min_temp=min_temp, max_temp=max_temp,
            warning_margin=dlg.warning_margin(), lot_id=dlg.lot_id(),
            auto_block=dlg.auto_block())
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Cadena de frío", message)
        if ok:
            self.refresh()

    def _on_resolve(self) -> None:
        eid = self._selected_excursion_id()
        if eid is None:
            return
        dlg = ResolveExcursionDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        note = dlg.note()
        if not note:
            QMessageBox.warning(self, "Cadena de frío", "Captura el motivo de la resolución.")
            return
        ok, message, _ = self._presenter.resolve_temperature_excursion(
            excursion_id=eid, resolution=dlg.resolution(), resolution_note=note)
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Cadena de frío", message)
        if ok:
            self.refresh()
