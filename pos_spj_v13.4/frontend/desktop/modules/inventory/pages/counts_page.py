"""Counts page (INV-25 / §17 / P0-C) — iniciar, capturar, confirmar, aprobar
y generar ajuste desde un conteo de inventario.

Lista los conteos recientes de la sucursal (folio, tipo, almacén, modalidad,
estado, creado) y permite operar sobre la fila seleccionada: iniciar un
conteo nuevo (una línea, producto vía búsqueda canónica), capturar la
cantidad contada, confirmar (calcula varianza y bloquea la captura), aprobar
(segregación real: quien contó no puede aprobar una varianza) y, ya
aprobado, generar el ajuste que aplica la varianza al inventario. Todos los
valores y mutaciones pasan por el presenter, que llama a los use cases
autorizados reales; esta página no tiene SQL ni lógica de negocio.
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
from frontend.desktop.components.dialogs import ConfirmationDialog
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.inventory.dialogs import (
    CreateCountDialog,
    RecordCountDialog,
)
from frontend.desktop.themes.tokens import Spacing


class CountsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryCountsPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Conteos",
            subtitle="Conteos cíclicos y físicos, reconteo y varianza.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.create_button = create_primary_button(text="Nuevo conteo")
        self.create_button.clicked.connect(self._on_create)
        actions.addWidget(self.create_button)
        self.record_button = create_secondary_button(text="Capturar")
        self.record_button.clicked.connect(self._on_record)
        actions.addWidget(self.record_button)
        self.confirm_button = create_secondary_button(text="Confirmar")
        self.confirm_button.clicked.connect(self._on_confirm)
        actions.addWidget(self.confirm_button)
        self.approve_button = create_secondary_button(text="Aprobar")
        self.approve_button.clicked.connect(self._on_approve)
        actions.addWidget(self.approve_button)
        self.generate_button = create_secondary_button(text="Generar ajuste")
        self.generate_button.clicked.connect(self._on_generate_adjustment)
        actions.addWidget(self.generate_button)
        layout.addLayout(actions)

        self._table = StandardTable(columns=[
            ColumnSpec("Folio", "text"),
            ColumnSpec("Tipo", "text"),
            ColumnSpec("Almacén", "text"),
            ColumnSpec("Modalidad", "text"),
            ColumnSpec("Estado", "status"),
            ColumnSpec("Creado", "text"),
        ])
        layout.addWidget(self._table)

    def refresh(self) -> None:
        table = self._presenter.counts()
        self._table.load_rows(table.rows, row_ids=table.row_ids)

    def _selected_count_id(self) -> str | None:
        cid = self._table.selected_row_id()
        if not cid:
            QMessageBox.information(
                self, "Conteos", "Selecciona un conteo de la lista.")
            return None
        return cid

    def _on_create(self) -> None:
        dlg = CreateCountDialog(self, product_provider=self._presenter.product_options)
        if dlg.exec_() != QDialog.Accepted:
            return
        product_id = dlg.product_id()
        if not product_id:
            QMessageBox.warning(self, "Conteos", "Selecciona un producto de la lista.")
            return
        ok, message, _ = self._presenter.create_count(
            product_id=product_id, count_type=dlg.count_type_code(), blind=dlg.blind())
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Conteos", message)
        if ok:
            self.refresh()

    def _on_record(self) -> None:
        cid = self._selected_count_id()
        if cid is None:
            return
        dlg = RecordCountDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        quantity = dlg.counted_quantity()
        if quantity is None:
            QMessageBox.warning(self, "Conteos", "Captura la cantidad contada.")
            return
        ok, message, _ = self._presenter.record_count(
            count_id=cid, counted_quantity=quantity)
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Conteos", message)
        if ok:
            self.refresh()

    def _on_confirm(self) -> None:
        cid = self._selected_count_id()
        if cid is None:
            return
        dlg = ConfirmationDialog(
            self, title="Confirmar conteo",
            message="Se calculará la varianza y ya no se podrá capturar. ¿Continuar?",
            confirm_text="Confirmar")
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message, _ = self._presenter.confirm_count(count_id=cid)
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Conteos", message)
        if ok:
            self.refresh()

    def _on_approve(self) -> None:
        cid = self._selected_count_id()
        if cid is None:
            return
        dlg = ConfirmationDialog(
            self, title="Aprobar conteo",
            message="El conteo quedará listo para generar su ajuste. ¿Continuar?",
            confirm_text="Aprobar")
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message, _ = self._presenter.approve_count(count_id=cid)
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Conteos", message)
        if ok:
            self.refresh()

    def _on_generate_adjustment(self) -> None:
        cid = self._selected_count_id()
        if cid is None:
            return
        dlg = ConfirmationDialog(
            self, title="Generar ajuste",
            message="Se creará un ajuste de inventario con la varianza del conteo."
                     " ¿Continuar?",
            confirm_text="Generar")
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message, _ = self._presenter.generate_adjustment_from_count(count_id=cid)
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Conteos", message)
        if ok:
            self.refresh()
