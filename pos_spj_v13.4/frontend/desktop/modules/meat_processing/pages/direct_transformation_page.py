"""Transformación directa (auditoría de Producción 32cfbf, 2026-10-16): elegir
un lote recibido de compra y despiezarlo en una sola acción.

Lista los lotes disponibles en el almacén de producción de productos con perfil
de rendimiento activo; los que Calidad no ha liberado aparecen con su motivo.
Sin SQL ni reglas: todo pasa por el presentador.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel

from frontend.desktop.components import (
    ColumnSpec,
    StandardPage,
    StandardTable,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.dialogs import ConfirmationDialog, MessageDialog


class DirectTransformationPage(StandardPage):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(
            parent, title="Transformación directa",
            subtitle="Despieza un lote ya recibido: pesa cada corte y regístralo en una sola "
                     "acción (orden, consumo, cortes, merma y costo).")
        self.setObjectName("meatDirectTransformationPage")
        self._presenter = presenter
        self._lots = []
        layout = self.content_layout

        self.notice = QLabel("", self)
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)

        acciones = QHBoxLayout()
        acciones.addStretch(1)
        self.refresh_button = create_secondary_button(text="Actualizar")
        self.refresh_button.clicked.connect(self.refresh)
        acciones.addWidget(self.refresh_button)
        self.transform_button = create_primary_button(text="Transformar lote")
        self.transform_button.clicked.connect(self._on_transform)
        acciones.addWidget(self.transform_button)
        layout.addLayout(acciones)

        self.table = StandardTable(columns=[
            ColumnSpec("Producto"), ColumnSpec("Recepción"), ColumnSpec("Proveedor"),
            ColumnSpec("Recibido"), ColumnSpec("Disponible kg", "numeric"),
            ColumnSpec("Almacén"), ColumnSpec("Calidad")])
        layout.addWidget(self.table)

    def ensure_loaded(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        motivo = self._presenter.unavailable_reason()
        self._lots = self._presenter.lots()
        self.table.load_rows(
            [[x.product_name, x.receipt_folio or "—", x.supplier_name or "—", x.received_at,
              f"{x.available_kg}", x.warehouse_name, x.quality_label] for x in self._lots],
            row_ids=[x.lot_id for x in self._lots])
        self.notice.setText(motivo or "")
        self.notice.setVisible(bool(motivo))
        self.transform_button.setEnabled(any(x.eligible for x in self._lots))

    def _selected_lot(self):
        lot_id = self.table.selected_row_id()
        lote = next((x for x in self._lots if x.lot_id == lot_id), None)
        if lote is None:
            MessageDialog.information(self, "Transformación directa",
                                      "Selecciona un lote de la lista.")
            return None
        if not lote.eligible:
            MessageDialog.warning(self, "Transformación directa", lote.blocked_reason)
            return None
        return lote

    def _on_transform(self) -> None:
        from frontend.desktop.modules.meat_processing.dialogs_direct_transformation import (
            DirectTransformationDialog,
        )
        from frontend.desktop.modules.meat_processing.dialogs_execution import (
            ExecutionResultDialog,
            ProductionAuthorizationDialog,
        )

        lote = self._selected_lot()
        if lote is None:
            return
        dlg = DirectTransformationDialog(self, lot=lote, presenter=self._presenter)
        if dlg.exec_() != QDialog.Accepted:
            return
        confirmar = ConfirmationDialog(
            self, title="Registrar transformación",
            message=(f"Se consumirán {dlg.input_weight()} kg de {lote.product_name} "
                     "y entrarán los cortes capturados a existencia. ¿Continuar?"),
            confirm_text="Registrar")
        if confirmar.exec_() != QDialog.Accepted:
            return
        datos = {"lot_id": lote.lot_id, "input_kg": dlg.input_weight(),
                 "outputs": dlg.outputs(),
                 "estimated_product_ids": dlg.estimated_product_ids(),
                 "estimate_reason": dlg.estimate_reason_text()}
        nombres = dlg.output_names()
        for _ in range(2):   # a lo sumo una autorización de rendimiento
            ok, mensaje, resultado = self._presenter.transform(**datos)
            if ok:
                ExecutionResultDialog(self, results=resultado.get("results") or [],
                                      message=mensaje, names=nombres).exec_()
                self.refresh()
                return
            if resultado.get("error_code") != "YIELD_AUTHORIZATION_REQUIRED":
                folio = resultado.get("folio")
                extra = (f"\n\nLa orden {folio} quedó en Órdenes; al repetir, la transformación "
                         "continúa desde donde quedó.") if folio else ""
                MessageDialog.warning(self, "Transformación directa", mensaje + extra)
                self.refresh()
                return
            auth = ProductionAuthorizationDialog(self, message=mensaje,
                                                 presenter=self._presenter)
            if auth.exec_() != QDialog.Accepted or not auth.authorizer_user_id:
                self.refresh()
                return
            datos["variance_authorizer_user_id"] = auth.authorizer_user_id
            datos["variance_reason"] = auth.reason
        MessageDialog.warning(self, "Transformación directa", "No se pudo registrar.")
