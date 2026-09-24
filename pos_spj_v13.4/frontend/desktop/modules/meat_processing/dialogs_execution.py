"""Ejecutar una orden de despiece (Fase 10, 2026-09-19).

Captura el peso REAL de la entrada y de cada corte —propuestos desde el
despiece capturado al liberar— y muestra el resultado: esperado, real,
diferencia, rendimiento y costo repartido de cada corte.

Sólo captura: quien decide es `ExecuteProcessingOrderUseCase`. Si falta
existencia de la entrada o un corte sale fuera de tolerancia, el cobro de la
orden pide la autorización en caliente de otro usuario (usuario, clave y
motivo), igual que el mostrador.
"""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtWidgets import QLabel

from frontend.desktop.components import (
    ColumnSpec,
    DecimalInput,
    FormDialog,
    PasswordInput,
    StandardLineEdit,
    StandardTable,
)

_TIPOS = {
    "MAIN_PRODUCT": "Producto principal", "CO_PRODUCT": "Coproducto",
    "BY_PRODUCT": "Subproducto", "WASTE": "Desperdicio", "LOSS": "Merma",
    "SEMI_FINISHED": "Semiterminado", "WORK_IN_PROGRESS": "En proceso",
    "REWORKABLE": "Reprocesable",
}


class ExecuteProcessingOrderDialog(FormDialog):
    """Pesos reales de la ejecución."""

    def __init__(self, parent=None, *, plan: dict) -> None:
        super().__init__(parent, title="Ejecutar orden de despiece", width=760)
        self.setObjectName("meatExecuteOrderDialog")
        self._plan = plan
        planeado = Decimal(str(plan.get("planned_weight") or 0))

        self.form.addRow("Entrada:", QLabel(str(plan.get("input_product_name") or ""), self))
        self.input_weight = DecimalInput(self, precision=3, minimum="0", suffix="kg")
        self.input_weight.set_decimal(planeado)
        self.form.addRow("Peso real consumido:", self.input_weight)

        ayuda = QLabel(
            "Captura el peso REAL de cada corte. Lo esperado viene del despiece de "
            "Productos; la diferencia se compara contra las tolerancias de Cárnico.", self)
        ayuda.setWordWrap(True)
        self.form.addRow(ayuda)

        self.table = StandardTable(columns=[
            ColumnSpec("Corte"), ColumnSpec("Tipo"), ColumnSpec("Esperado kg", "numeric"),
            ColumnSpec("Real kg", "numeric")])
        self.form.addRow(self.table)

        self._campos: dict[str, DecimalInput] = {}
        self._salidas = list(plan.get("outputs") or [])
        filas = []
        for salida in self._salidas:
            campo = DecimalInput(self, precision=3, minimum="0", suffix="kg")
            campo.set_decimal(salida.expected_weight)
            self._campos[salida.product_id] = campo
            filas.append([salida.product_name or salida.product_id,
                          _TIPOS.get(salida.output_type, salida.output_type),
                          f"{salida.expected_weight}", ""])
        self.table.load_rows(filas, row_ids=[s.product_id for s in self._salidas])
        # Los pesos se capturan en campos, no dentro de la tabla: la tabla es el
        # plan (lo esperado) y los campos, lo real.
        for salida in self._salidas:
            self.form.addRow(f"Real — {salida.product_name or salida.product_id}:",
                             self._campos[salida.product_id])

        self._error = QLabel("", self)
        self._error.setObjectName("textDanger")
        self._error.setWordWrap(True)
        self.form.addRow(self._error)
        box = self.add_button_box(ok_text="Ejecutar y cerrar orden")
        box.accepted.disconnect()
        box.accepted.connect(self._accept_if_valid)

    def input_weight_value(self):
        return self.input_weight.decimal_value()

    def outputs(self) -> list[dict]:
        return [{"product_id": pid, "weight": campo.decimal_value() or Decimal("0")}
                for pid, campo in self._campos.items()]

    def _accept_if_valid(self) -> None:
        peso = self.input_weight_value()
        if not peso or peso <= 0:
            self._error.setText("Captura el peso real consumido de la entrada.")
            return
        if not any((c.decimal_value() or 0) > 0 for c in self._campos.values()):
            self._error.setText("Captura el peso real de al menos un corte.")
            return
        self.accept()


class ProductionAuthorizationDialog(FormDialog):
    """Autorización en caliente de producción: producir sin existencia o un
    rendimiento fuera de tolerancia. Otro usuario, con su clave y un motivo."""

    def __init__(self, parent=None, *, message: str, presenter) -> None:
        super().__init__(parent, title="Autorización de producción")
        self.setObjectName("meatProductionAuthorizationDialog")
        self._presenter = presenter
        self.authorizer_user_id: str | None = None
        self.reason: str | None = None

        aviso = QLabel(message, self)
        aviso.setWordWrap(True)
        self.form.addRow(aviso)
        self._user = StandardLineEdit(self, placeholder="Usuario de quien autoriza")
        self._password = PasswordInput(self, placeholder="Clave de quien autoriza")
        self._reason = StandardLineEdit(self, placeholder="Motivo (obligatorio)")
        self.form.addRow("Autoriza", self._user)
        self.form.addRow("Clave", self._password)
        self.form.addRow("Motivo", self._reason)
        self._error = QLabel("", self)
        self._error.setObjectName("textDanger")
        self._error.setWordWrap(True)
        self.form.addRow(self._error)
        box = self.add_button_box(ok_text="Autorizar y continuar")
        box.accepted.disconnect()
        box.accepted.connect(self._authorize)

    def _authorize(self) -> None:
        motivo = self._reason.value().strip()
        if not motivo:
            self._error.setText("Captura el motivo de la autorización.")
            return
        user_id, problema = self._presenter.verify_authorizer(
            self._user.value().strip(), self._password.value())
        if user_id is None:
            self._error.setText(problema)
            return
        self.authorizer_user_id, self.reason = user_id, motivo
        self.accept()


class ExecutionResultDialog(FormDialog):
    """Lo que dejó la ejecución, corte por corte (§13)."""

    def __init__(self, parent=None, *, results: list[dict], message: str) -> None:
        super().__init__(parent, title="Orden ejecutada", width=820)
        self.setObjectName("meatExecutionResultDialog")
        resumen = QLabel(message, self)
        resumen.setWordWrap(True)
        self.form.addRow(resumen)
        self.table = StandardTable(columns=[
            ColumnSpec("Corte"), ColumnSpec("Esperado kg", "numeric"),
            ColumnSpec("Real kg", "numeric"), ColumnSpec("Diferencia kg", "numeric"),
            ColumnSpec("Rendimiento"), ColumnSpec("Costo/kg", "numeric"),
            ColumnSpec("Costo total", "numeric")])
        self.table.load_rows(
            [[r.get("product_id", "")[-8:], str(r.get("expected_weight", "")),
              str(r.get("actual_weight", "")), str(r.get("difference_weight", "")),
              f"{r.get('yield_pct', '')}%", str(r.get("unit_cost", "")),
              str(r.get("allocated_cost", ""))] for r in results],
            row_ids=[str(i) for i in range(len(results))])
        self.form.addRow(self.table)
        self.add_button_box(ok_text="Cerrar")
