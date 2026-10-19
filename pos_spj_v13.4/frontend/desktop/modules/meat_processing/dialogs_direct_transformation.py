"""Captura de una transformación directa (auditoría de Producción 32cfbf).

Muestra lo esperado por el perfil de rendimiento activo (sólo lectura) para los
kilos de entrada, y pide el peso REAL de cada salida, vacío hasta pesar. Si una
salida no se pesó, «Usar lo esperado en las vacías» la marca ESTIMADO y pide
motivo. El balance dice qué falta para cuadrar la entrada: nada se ajusta en
silencio. La pantalla no calcula: lo esperado lo da el presentador.
"""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtWidgets import QFormLayout, QLabel, QPushButton, QWidget

from frontend.desktop.components import (
    ColumnSpec,
    DecimalInput,
    FormDialog,
    StandardLineEdit,
    StandardTable,
)


class DirectTransformationDialog(FormDialog):
    def __init__(self, parent=None, *, lot, presenter) -> None:
        super().__init__(parent, title="Transformación directa", width=820)
        self.setObjectName("meatDirectTransformationDialog")
        self._lot = lot
        self._presenter = presenter
        self._campos: dict[str, DecimalInput] = {}
        self._esperado: dict[str, Decimal] = {}
        self._estimadas: set[str] = set()
        self._llenando = False
        self._filas = ()

        origen = QLabel(
            f"{lot.product_name} — lote de {lot.receipt_folio or 'compra'}"
            f"{' · ' + lot.supplier_name if lot.supplier_name else ''}"
            f" · recibido {lot.received_at} · disponible {lot.available_kg} kg", self)
        origen.setWordWrap(True)
        self.form.addRow(origen)
        self.input_kg = DecimalInput(self, precision=3, minimum="0", suffix="kg")
        self.input_kg.set_decimal(lot.available_kg)
        self.input_kg.value_changed.connect(self._refresh_preview)
        self.form.addRow("Kilos a transformar:", self.input_kg)

        self.version = QLabel("", self)
        self.version.setWordWrap(True)
        self.form.addRow(self.version)
        self.table = StandardTable(columns=[
            ColumnSpec("Salida"), ColumnSpec("Tipo"), ColumnSpec("% esperado", "numeric"),
            ColumnSpec("Esperado kg", "numeric")])
        self.form.addRow(self.table)
        # Las capturas reales cambian con lo esperado: viven en su propio
        # contenedor, que se reconstruye; el pie del formulario no se toca.
        self._real_box = QWidget(self)
        self._real_form = QFormLayout(self._real_box)
        self._real_form.setContentsMargins(0, 0, 0, 0)
        self.form.addRow(self._real_box)

        self.estimate_button = QPushButton("Usar lo esperado en las vacías", self)
        self.estimate_button.clicked.connect(self._use_expected_for_empty)
        self.estimate_reason = StandardLineEdit(
            self, placeholder="Motivo del estimado (obligatorio si hay salidas estimadas)")
        self.estimate_label = QLabel("Motivo del estimado:", self)
        self.balance = QLabel("", self)
        self.balance.setWordWrap(True)
        self._error = QLabel("", self)
        self._error.setObjectName("textDanger")
        self._error.setWordWrap(True)
        self.form.addRow(self.estimate_button)
        self.form.addRow(self.estimate_label, self.estimate_reason)
        self.form.addRow(self.balance)
        self.form.addRow(self._error)
        self._refresh_preview()
        self.add_button_box(ok_text="Registrar transformación",
                            on_accept=self._accept_if_valid)

    # ── vista previa ────────────────────────────────────────────────────────
    def _refresh_preview(self) -> None:
        kg = self.input_kg.decimal_value() or Decimal("0")
        vista = self._presenter.preview(self._lot.product_id, kg)
        capturado = {pid: c.decimal_value() for pid, c in self._campos.items()}
        while self._real_form.rowCount():
            self._real_form.removeRow(0)
        self._campos.clear()
        if vista.problem:
            self.version.setText(vista.problem)
            self.table.load_rows([], row_ids=[])
            self._filas = ()
            self._error.setText(vista.problem)
            self._sync()
            return
        self.version.setText(f"Perfil de rendimiento: {vista.effective_version or 'activo'}")
        self._filas = vista.rows
        self.table.load_rows(
            [[f.product_name, f.type_label, f"{f.expected_pct}", f"{f.expected_kg}"]
             for f in vista.rows], row_ids=[f.product_id for f in vista.rows])
        for f in vista.rows:
            campo = DecimalInput(self, precision=3, minimum="0", suffix="kg", nullable=True)
            campo.setPlaceholderText("Sin pesar")  # vacío ≠ 0: 0 es «no salió nada»
            if capturado.get(f.product_id) is not None:
                campo.set_decimal(capturado[f.product_id])
            campo.value_changed.connect(lambda pid=f.product_id: self._on_real_changed(pid))
            self._campos[f.product_id] = campo
            self._esperado[f.product_id] = f.expected_kg
            self._real_form.addRow(f"Real — {f.product_name}:", campo)
        self._estimadas &= set(self._campos)
        if self._estimadas:
            self._use_expected_for(self._estimadas)
        self._error.setText("")
        self._sync()

    # ── estimado explícito ──────────────────────────────────────────────────
    def _use_expected_for(self, ids) -> None:
        self._llenando = True
        try:
            for pid in ids:
                self._campos[pid].set_decimal(self._esperado.get(pid, Decimal("0")))
        finally:
            self._llenando = False

    def _use_expected_for_empty(self) -> None:
        vacias = {pid for pid, c in self._campos.items() if c.decimal_value() is None}
        self._use_expected_for(vacias)
        self._estimadas |= vacias
        self._sync()

    def _on_real_changed(self, pid: str) -> None:
        if not self._llenando:
            self._estimadas.discard(pid)
        self._sync()

    def _sync(self) -> None:
        hay = bool(self._estimadas)
        self.estimate_label.setVisible(hay)
        self.estimate_reason.setVisible(hay)
        entrada = self.input_kg.decimal_value() or Decimal("0")
        stock = sum((self._campos[f.product_id].decimal_value() or Decimal("0")
                     for f in self._filas if f.goes_to_stock and f.product_id in self._campos),
                    Decimal("0"))
        merma = sum((self._campos[f.product_id].decimal_value() or Decimal("0")
                     for f in self._filas if not f.goes_to_stock and f.product_id in self._campos),
                    Decimal("0"))
        diferencia = entrada - stock - merma
        nombres = {f.product_id: f.product_name for f in self._filas}
        estimado = (" · ESTIMADO (no pesado): "
                    + ", ".join(nombres.get(p, "") for p in sorted(self._estimadas))) if hay else ""
        self.balance.setText(
            f"Entrada {entrada} kg = salidas a existencia {stock} kg + merma capturada "
            f"{merma} kg + diferencia sin clasificar {diferencia} kg{estimado}")

    # ── resultado ───────────────────────────────────────────────────────────
    def input_weight(self) -> Decimal:
        return self.input_kg.decimal_value() or Decimal("0")

    def outputs(self) -> list[dict]:
        return [{"product_id": pid, "weight": c.decimal_value() or Decimal("0")}
                for pid, c in self._campos.items()]

    def output_names(self) -> dict[str, str]:
        return {f.product_id: f.product_name for f in self._filas}

    def estimated_product_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._estimadas))

    def estimate_reason_text(self) -> str | None:
        return (self.estimate_reason.value().strip() or None) if self._estimadas else None

    def problem(self) -> str | None:
        entrada = self.input_weight()
        if entrada <= 0:
            return "Captura los kilos a transformar."
        if entrada > self._lot.available_kg:
            return f"El lote sólo tiene {self._lot.available_kg} kg disponibles."
        if not self._filas:
            return self._error.text() or "No hay salidas que capturar."
        vacias = [f.product_name for f in self._filas
                  if self._campos[f.product_id].decimal_value() is None]
        if vacias:
            return ("Falta el peso real de: " + ", ".join(vacias) + ". Pésalas, captura 0 si "
                    "no salió nada, o usa lo esperado (queda como ESTIMADO).")
        if self._estimadas and not self.estimate_reason.value().strip():
            return "Captura el motivo del estimado."
        return None

    def _accept_if_valid(self) -> None:
        problema = self.problem()
        self._error.setText(problema or "")
        if problema is None:
            self.accept()
