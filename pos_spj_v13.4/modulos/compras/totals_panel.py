# modulos/compras/totals_panel.py — SPJ POS v13.4
"""
TotalsPanel — subtotals / IVA / total display + payment form.

Signals:
    iva_changed(bool)       — IVA checkbox toggled
    pago_changed(str)       — payment method combo changed
    condicion_changed(str)  — condicion_pago changed

Usage:
    panel = TotalsPanel(parent=self)
    panel.update_totals(subtotal, iva, descuento, flete, otros)
"""
from __future__ import annotations
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
    QLabel, QCheckBox, QComboBox, QSpinBox, QDoubleSpinBox,
)
from PyQt5.QtCore import pyqtSignal, QDate
from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.ui_components import create_combo

_PAGO_ITEMS = [
    ("CONTADO (Efectivo)",          "CONTADO"),
    ("CREDITO (Cuentas por Pagar)", "CREDITO"),
    ("TRANSFERENCIA",               "TRANSFERENCIA"),
    ("CHEQUE",                      "CHEQUE"),
]


class TotalsPanel(QWidget):
    """
    Compact totals card: 2-col grid (subtotal / descuento / IVA / flete)
    + large total label + payment method/condition row.
    No SQL, no business logic.
    """
    iva_changed       = pyqtSignal(bool)
    pago_changed      = pyqtSignal(str)
    condicion_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    # ── Public API ────────────────────────────────────────────────────────────

    def update_totals(self, subtotal: float = 0, iva: float = 0,
                      descuento: float = 0, flete: float = 0,
                      otros: float = 0) -> None:
        total = subtotal + iva + flete + otros - descuento
        self._lbl_subtotal.setText(f"${subtotal:,.2f}")
        self._lbl_descuento.setText(f"${descuento:,.2f}")
        self._lbl_iva.setText(f"${iva:,.2f}")
        self._lbl_flete.setText(f"${flete + otros:,.2f}")
        self.lbl_total.setText(f"${total:,.2f}")
        if iva > 0:
            self._lbl_iva.show()
            self._lbl_iva_hdr.show()
        else:
            self._lbl_iva.hide()
            self._lbl_iva_hdr.hide()

    def get_pago(self) -> str:
        return self.cmb_pago.currentData() or self.cmb_pago.currentText()

    def get_condicion(self) -> str:
        return self._cmb_condicion.currentText()

    def get_plazo(self) -> int:
        return self._spin_plazo.value()

    def get_flete(self) -> float:
        return self._spin_flete.value()

    def get_otros(self) -> float:
        return self._spin_otros.value()

    def is_iva_checked(self) -> bool:
        return self._chk_iva.isChecked()

    # ── Private ───────────────────────────────────────────────────────────────

    def _fl(self, txt: str) -> QLabel:
        l = QLabel(txt.upper())
        l.setStyleSheet(
            f"font-size:9px;font-weight:700;color:{Colors.NEUTRAL.SLATE_500};"
            "letter-spacing:0.05em;background:transparent;"
        )
        return l

    def _fv(self, initial="$0.00", color=None) -> QLabel:
        l = QLabel(initial)
        l.setObjectName("caption")
        if color:
            l.setStyleSheet(f"color:{color};font-weight:700;background:transparent;")
        return l

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(Spacing.SM + 2, Spacing.SM, Spacing.SM + 2, Spacing.SM)
        lay.setSpacing(Spacing.SM)

        # 2-column grid
        grid = QGridLayout()
        grid.setSpacing(Spacing.XS)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self._lbl_subtotal  = self._fv()
        self._lbl_descuento = self._fv(color=Colors.WARNING_BASE)
        self._lbl_iva       = self._fv(color=Colors.INFO_BASE)
        self._lbl_iva_hdr   = self._fl("Impuestos (IVA)")
        self._lbl_flete     = self._fv()

        grid.addWidget(self._fl("Subtotal"),         0, 0)
        grid.addWidget(self._fl("Descuento"),         0, 1)
        grid.addWidget(self._lbl_subtotal,            1, 0)
        grid.addWidget(self._lbl_descuento,           1, 1)
        grid.addWidget(self._lbl_iva_hdr,             2, 0)
        grid.addWidget(self._fl("Flete / Otros"),     2, 1)
        grid.addWidget(self._lbl_iva,                 3, 0)
        grid.addWidget(self._lbl_flete,               3, 1)
        self._lbl_iva.hide()
        self._lbl_iva_hdr.hide()
        lay.addLayout(grid)

        # IVA checkbox + hidden cargo spinboxes (kept for compat)
        self._chk_iva = QCheckBox("IVA 16%")
        self._chk_iva.stateChanged.connect(lambda s: self.iva_changed.emit(bool(s)))
        lay.addWidget(self._chk_iva)

        self._spin_flete = QDoubleSpinBox()
        self._spin_flete.setRange(0, 999999); self._spin_flete.setDecimals(2)
        self._spin_flete.setPrefix("$ "); self._spin_flete.hide()
        self._spin_otros = QDoubleSpinBox()
        self._spin_otros.setRange(0, 999999); self._spin_otros.setDecimals(2)
        self._spin_otros.setPrefix("$ "); self._spin_otros.hide()
        lay.addWidget(self._spin_flete)
        lay.addWidget(self._spin_otros)

        # Separator
        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"border:none;border-top:1px solid {Colors.NEUTRAL.SLATE_200};")
        lay.addWidget(sep)

        # Total
        total_row = QHBoxLayout()
        total_col = QVBoxLayout(); total_col.setSpacing(2)
        hdr_total = QLabel("TOTAL DOCUMENTO")
        hdr_total.setStyleSheet(
            f"font-size:9px;font-weight:700;color:{Colors.NEUTRAL.SLATE_500};"
            "letter-spacing:0.08em;background:transparent;"
        )
        self.lbl_total = QLabel("$0.00")
        self.lbl_total.setStyleSheet(
            f"font-size:28px;font-weight:700;color:{Colors.ACCENT_BASE};"
            "background:transparent;letter-spacing:-0.02em;"
        )
        total_col.addWidget(hdr_total)
        total_col.addWidget(self.lbl_total)
        total_row.addLayout(total_col)
        lay.addLayout(total_row)

        # Payment form
        pay_grid = QGridLayout()
        pay_grid.setSpacing(Spacing.XS)
        pay_grid.setColumnStretch(0, 1); pay_grid.setColumnStretch(1, 1)

        self.cmb_pago = create_combo(self)
        for label, data in _PAGO_ITEMS:
            self.cmb_pago.addItem(label, data)
        self.cmb_pago.currentIndexChanged.connect(
            lambda _: self.pago_changed.emit(self.get_pago()))

        self._cmb_condicion = create_combo(self)
        self._cmb_condicion.addItems(["Liquidado", "Crédito", "Parcial"])
        self._cmb_condicion.currentTextChanged.connect(self._on_condicion_changed)

        self._spin_plazo = QSpinBox()
        self._spin_plazo.setRange(0, 365)
        self._spin_plazo.setSuffix(" días")
        self._spin_plazo.setValue(30)

        self._lbl_vence = QLabel("—")
        self._lbl_vence.setObjectName("caption")

        pay_grid.addWidget(self._fl("Método / Forma"),  0, 0, 1, 2)
        pay_grid.addWidget(self.cmb_pago,               1, 0, 1, 2)
        pay_grid.addWidget(self._fl("Condición"),       2, 0)
        pay_grid.addWidget(self._fl("Plazo"),           2, 1)
        pay_grid.addWidget(self._cmb_condicion,         3, 0)
        pay_grid.addWidget(self._spin_plazo,            3, 1)
        pay_grid.addWidget(self._fl("Vence"),           4, 0)
        pay_grid.addWidget(self._lbl_vence,             5, 0, 1, 2)
        lay.addLayout(pay_grid)

    def _on_condicion_changed(self, condicion: str) -> None:
        es_credito = condicion.lower() != "liquidado"
        self._spin_plazo.setEnabled(es_credito)
        if es_credito:
            vence = QDate.currentDate().addDays(self._spin_plazo.value())
            self._lbl_vence.setText(f"Vence: {vence.toString('dd/MMM/yyyy')}")
        else:
            self._lbl_vence.setText("Vence: N/A")
        self.condicion_changed.emit(condicion)
