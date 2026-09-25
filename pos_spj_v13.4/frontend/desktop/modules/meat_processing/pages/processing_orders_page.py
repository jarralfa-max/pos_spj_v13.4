"""Órdenes page (PROC-23, §12/§13) — crear, aprobar, preparar, liberar, ejecutar
y cerrar órdenes de procesamiento.

Preparar congela la definición de Productos y reserva los insumos en
Inventario; sólo una orden preparada se libera.

Lista las órdenes recientes de la sucursal (tipo, estado, cantidad, peso,
creada) y permite actuar sobre la fila seleccionada. Todos los valores y
mutaciones pasan por el presenter, que llama a los use cases autorizados
reales (backend/application/meat_processing/use_cases); esta página no
tiene SQL ni lógica de negocio — sólo confirma intención y muestra el
resultado. Mirrors frontend/desktop/modules/inventory/pages/adjustments_page.py.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec,
    PageHeader,
    StandardTable,
    create_danger_button,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.dialogs import ConfirmationDialog
from frontend.desktop.modules.meat_processing.dialogs import CreateProcessingOrderDialog
from frontend.desktop.themes.tokens import Spacing


class ProcessingOrdersPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("meatProcessingOrdersPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Órdenes",
            subtitle="Órdenes de procesamiento y su ciclo de vida.", compact=True)
        layout.addWidget(self.header)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.create_button = create_primary_button(text="Nueva orden")
        self.create_button.clicked.connect(self._on_create)
        actions.addWidget(self.create_button)
        self.approve_button = create_secondary_button(text="Aprobar")
        self.approve_button.clicked.connect(self._on_approve)
        actions.addWidget(self.approve_button)
        self.prepare_button = create_secondary_button(text="Preparar")
        self.prepare_button.setToolTip(
            "Congelar la definición del producto y reservar los insumos en Inventario.")
        self.prepare_button.clicked.connect(self._on_prepare)
        actions.addWidget(self.prepare_button)
        self.release_button = create_secondary_button(text="Liberar")
        self.release_button.clicked.connect(self._on_release)
        actions.addWidget(self.release_button)
        self.execute_button = create_primary_button(text="Ejecutar")
        self.execute_button.setToolTip(
            "Consumir lo reservado, capturar las salidas, pedir calidad y costeo, y cerrar.")
        self.execute_button.clicked.connect(self._on_execute)
        actions.addWidget(self.execute_button)
        self.close_button = create_danger_button(text="Cerrar")
        self.close_button.clicked.connect(self._on_close)
        actions.addWidget(self.close_button)
        layout.addLayout(actions)

        self._table = StandardTable(columns=[
            ColumnSpec("Folio", "text"),
            ColumnSpec("Tipo", "text"),
            ColumnSpec("Estado", "status"),
            ColumnSpec("Cantidad", "text"),
            ColumnSpec("Peso", "text"),
            ColumnSpec("Creada", "text"),
        ])
        layout.addWidget(self._table)

    def ensure_loaded(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        table = self._presenter.orders()
        self._table.load_rows(table.rows, row_ids=table.row_ids)

    def _selected_order_id(self) -> str | None:
        oid = self._table.selected_row_id()
        if not oid:
            QMessageBox.information(self, "Órdenes", "Selecciona una orden de la lista.")
            return None
        return oid

    def _on_create(self) -> None:
        dlg = CreateProcessingOrderDialog(
            self, process_types=self._presenter.process_types(),
            product_provider=self._presenter.product_options)
        if dlg.exec_() != QDialog.Accepted:
            return
        product_id = dlg.product_id()
        if not product_id:
            QMessageBox.warning(self, "Órdenes", "Selecciona un producto de la lista.")
            return
        ok, message, _ = self._presenter.create_order(
            process_type=dlg.process_type(), target_product_id=product_id,
            planned_quantity=dlg.planned_quantity(), planned_weight=dlg.planned_weight())
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Órdenes", message)
        if ok:
            self.refresh()

    def _on_approve(self) -> None:
        oid = self._selected_order_id()
        if oid is None:
            return
        dlg = ConfirmationDialog(
            self, title="Aprobar orden",
            message="La orden quedará lista para liberarse. ¿Continuar?",
            confirm_text="Aprobar")
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message, _ = self._presenter.approve_order(order_id=oid)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Órdenes", message)
        if ok:
            self.refresh()

    def _on_prepare(self) -> None:
        oid = self._selected_order_id()
        if oid is None:
            return
        ok, message, datos = self._presenter.prepare_order(order_id=oid)
        aviso = QMessageBox.information if ok and datos.get("ready", True) else QMessageBox.warning
        aviso(self, "Órdenes", message)
        self.refresh()

    def _on_release(self) -> None:
        oid = self._selected_order_id()
        if oid is None:
            return
        dlg = ConfirmationDialog(
            self, title="Liberar orden",
            message="La orden pasará a ejecución. ¿Continuar?", confirm_text="Liberar")
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message, _ = self._presenter.release_order(order_id=oid)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Órdenes", message)
        if ok:
            self.refresh()

    def _on_execute(self) -> None:
        """Ejecutar la orden preparada. Si una salida queda fuera de tolerancia,
        se pide la autorización de otro usuario y se reintenta: el caso de uso
        es reanudable y no duplica lo ya hecho."""
        from frontend.desktop.modules.meat_processing.dialogs_execution import (
            ExecuteProcessingOrderDialog,
            ExecutionResultDialog,
            ProductionAuthorizationDialog,
        )

        oid = self._selected_order_id()
        if oid is None:
            return
        plan = self._presenter.execution_plan(oid)
        if plan is None:
            QMessageBox.warning(self, "Órdenes", "No se pudo leer la orden.")
            return
        if not plan.get("has_definition"):
            QMessageBox.warning(
                self, "Órdenes",
                "La orden no tiene su definición congelada: prepárala primero.")
            return
        if not any(e.get("reserved_weight") for e in plan.get("inputs") or []):
            QMessageBox.warning(
                self, "Órdenes",
                "La orden no tiene insumos reservados en Inventario: prepárala primero.")
            return
        dlg = ExecuteProcessingOrderDialog(self, plan=plan)
        if dlg.exec_() != QDialog.Accepted:
            return
        nombres = {s["product_id"]: s["product_name"] for s in plan.get("outputs") or []}
        datos = {"order_id": oid, "inputs": dlg.inputs(), "outputs": dlg.outputs()}
        for _ in range(2):   # a lo sumo una autorización de rendimiento
            ok, message, resultado = self._presenter.execute_order(**datos)
            if ok:
                ExecutionResultDialog(self, results=resultado.get("results") or [],
                                      message=message, names=nombres).exec_()
                self.refresh()
                return
            if resultado.get("error_code") != "YIELD_AUTHORIZATION_REQUIRED":
                QMessageBox.warning(self, "Órdenes", message)
                self.refresh()
                return
            auth = ProductionAuthorizationDialog(self, message=message,
                                                 presenter=self._presenter)
            if auth.exec_() != QDialog.Accepted or not auth.authorizer_user_id:
                self.refresh()
                return
            datos["variance_authorizer_user_id"] = auth.authorizer_user_id
            datos["variance_reason"] = auth.reason
        QMessageBox.warning(self, "Órdenes", "No se pudo ejecutar la orden.")

    def _on_close(self) -> None:
        oid = self._selected_order_id()
        if oid is None:
            return
        dlg = ConfirmationDialog(
            self, title="Cerrar orden",
            message="El cierre es terminal e irreversible por este medio. ¿Continuar?",
            confirm_text="Cerrar")
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message, _ = self._presenter.close_order(order_id=oid)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Órdenes", message)
        if ok:
            self.refresh()
