"""Ejecutar una orden de procesamiento — cualquier proceso, cualquier producto.

Captura el peso REAL de cada insumo reservado y de cada salida. Lo esperado y
los insumos salen de la definición congelada de la orden (no de Productos en
vivo); lo reservado, de Inventario. La pantalla no calcula nada: sólo captura y
muestra. Si una salida queda fuera de tolerancia, el caso de uso pide la
autorización en caliente de otro usuario (usuario, clave y motivo).
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


def _get(fila, clave, defecto=None):
    return fila.get(clave, defecto) if isinstance(fila, dict) else getattr(fila, clave, defecto)


class ExecuteProcessingOrderDialog(FormDialog):
    """Pesos reales de la ejecución."""

    def __init__(self, parent=None, *, plan: dict) -> None:
        super().__init__(parent, title="Ejecutar orden", width=780)
        self.setObjectName("meatExecuteOrderDialog")
        self._plan = plan
        version = QLabel(f"Definición congelada: {plan.get('effective_version') or '—'}", self)
        version.setWordWrap(True)
        self.form.addRow(version)

        self.inputs_table = StandardTable(columns=[
            ColumnSpec("Insumo"), ColumnSpec("Reservado kg", "numeric"), ColumnSpec("Lotes")])
        self.form.addRow(self.inputs_table)
        self._entradas: dict[str, DecimalInput] = {}
        filas = []
        for entrada in plan.get("inputs") or []:
            pid = _get(entrada, "product_id")
            reservado = Decimal(str(_get(entrada, "reserved_weight") or 0))
            lotes = [lote for lote in (_get(entrada, "lots") or []) if _get(lote, "lot_id")]
            campo = DecimalInput(self, precision=3, minimum="0", suffix="kg")
            campo.set_decimal(reservado)
            self._entradas[pid] = campo
            filas.append([_get(entrada, "product_name") or "", f"{reservado}",
                          f"{len(lotes)} lote(s)" if lotes else "Sin lote"])
        self.inputs_table.load_rows(filas, row_ids=list(self._entradas))
        for entrada in plan.get("inputs") or []:
            self.form.addRow(f"Consumido — {_get(entrada, 'product_name') or ''}:",
                             self._entradas[_get(entrada, "product_id")])

        ayuda = QLabel(
            "Captura el peso REAL de cada salida. Lo esperado sale de la definición "
            "congelada; las salidas que requieren inspección entran retenidas hasta que "
            "Calidad las libere.", self)
        ayuda.setWordWrap(True)
        self.form.addRow(ayuda)

        self.table = StandardTable(columns=[
            ColumnSpec("Salida"), ColumnSpec("Tipo"), ColumnSpec("Esperado kg", "numeric"),
            ColumnSpec("Calidad")])
        self.form.addRow(self.table)
        self._campos: dict[str, DecimalInput] = {}
        self._salidas = list(plan.get("outputs") or [])
        filas = []
        for salida in self._salidas:
            pid = _get(salida, "product_id")
            campo = DecimalInput(self, precision=3, minimum="0", suffix="kg")
            campo.set_decimal(_get(salida, "expected_weight") or Decimal("0"))
            self._campos[pid] = campo
            filas.append([_get(salida, "product_name") or "",
                          _TIPOS.get(_get(salida, "output_type"), _get(salida, "output_type")),
                          f"{_get(salida, 'expected_weight')}",
                          "Inspección" if _get(salida, "quality_gate") else "Directa"])
        self.table.load_rows(filas, row_ids=[_get(s, "product_id") for s in self._salidas])
        for salida in self._salidas:
            self.form.addRow(f"Real — {_get(salida, 'product_name') or ''}:",
                             self._campos[_get(salida, "product_id")])

        self._error = QLabel("", self)
        self._error.setObjectName("textDanger")
        self._error.setWordWrap(True)
        self.form.addRow(self._error)
        box = self.add_button_box(ok_text="Ejecutar y cerrar orden")
        box.accepted.disconnect()
        box.accepted.connect(self._accept_if_valid)

    def inputs(self) -> list[dict]:
        return [{"product_id": pid, "weight": campo.decimal_value() or Decimal("0")}
                for pid, campo in self._entradas.items()]

    def outputs(self) -> list[dict]:
        return [{"product_id": pid, "weight": campo.decimal_value() or Decimal("0")}
                for pid, campo in self._campos.items()]

    def _accept_if_valid(self) -> None:
        if not any((c.decimal_value() or 0) > 0 for c in self._entradas.values()):
            self._error.setText("Captura el peso real consumido.")
            return
        if not any((c.decimal_value() or 0) > 0 for c in self._campos.values()):
            self._error.setText("Captura el peso real de al menos una salida.")
            return
        self.accept()


class ProductionAuthorizationDialog(FormDialog):
    """Autorización en caliente de un rendimiento fuera de tolerancia: otro
    usuario, con su clave y un motivo. Producir sin existencia ya no se
    autoriza: sin reserva real en Inventario no hay consumo."""

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
    """Lo que dejó la ejecución, salida por salida (§13). Sin costos: los asigna
    Costos y se consultan en Rendimientos."""

    def __init__(self, parent=None, *, results: list[dict], message: str,
                 names: dict | None = None) -> None:
        super().__init__(parent, title="Orden ejecutada", width=820)
        self.setObjectName("meatExecutionResultDialog")
        nombres = names or {}
        resumen = QLabel(message, self)
        resumen.setWordWrap(True)
        self.form.addRow(resumen)
        self.table = StandardTable(columns=[
            ColumnSpec("Salida"), ColumnSpec("Esperado kg", "numeric"),
            ColumnSpec("Real kg", "numeric"), ColumnSpec("Diferencia kg", "numeric"),
            ColumnSpec("Rendimiento"), ColumnSpec("Variación")])
        filas = []
        for r in results:
            variacion = r.get("variance_pct")
            filas.append([nombres.get(r.get("product_id"), ""), str(r.get("expected_weight", "")),
                          str(r.get("actual_weight", "")), str(r.get("difference_weight", "")),
                          f"{r.get('yield_pct', '')}%",
                          f"{variacion}%" if variacion is not None else "—"])
        self.table.load_rows(filas, row_ids=[str(i) for i in range(len(results))])
        self.form.addRow(self.table)
        self.add_button_box(ok_text="Cerrar")
