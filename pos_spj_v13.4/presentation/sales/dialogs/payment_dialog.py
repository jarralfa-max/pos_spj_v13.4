from __future__ import annotations

from typing import Any, Dict
from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QFrame, QLabel, QFormLayout, QComboBox, QDoubleSpinBox,
    QHBoxLayout, QCheckBox, QSpinBox, QPushButton)
from PyQt5.QtCore import Qt


class DialogoPago(QDialog):
    def __init__(self, total_a_pagar: float, parent: QWidget = None,
                 loyalty_balance: Dict = None, loyalty_preview_provider=None):
        super().__init__(parent)
        self.setWindowTitle("Cobrar")
        self.setModal(True)
        self.setMinimumSize(460, 400)
        self.resize(500, 460)
        # ISSUE 4 FIX: objectName para que el QSS global pueda estilizar el diálogo
        self.setObjectName("paymentDialog")
        self.total_a_pagar = float(total_a_pagar) if total_a_pagar is not None else 0.0
        self.total_original = self.total_a_pagar
        self.efectivo_recibido = 0.0
        self.cambio = 0.0
        self.forma_pago = "Efectivo"
        self.saldo_credito = 0.0
        self._loyalty = loyalty_balance or {}
        self._loyalty_preview_provider = loyalty_preview_provider
        self.puntos_a_canjear = 0
        self.descuento_puntos = 0.0
        self.init_ui()
        self.conectar_eventos()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 14, 16, 14)

        # ── Header: Total prominente ────────────────────────────────────────
        header = QFrame()
        header.setObjectName("paymentHeader")
        hdr_lay = QVBoxLayout(header)
        hdr_lay.setContentsMargins(12, 10, 12, 10)
        hdr_lay.setSpacing(2)
        lbl_caption = QLabel("TOTAL A COBRAR")
        lbl_caption.setObjectName("paymentCaption")
        lbl_caption.setAlignment(Qt.AlignCenter)
        self.lbl_total = QLabel(f"${self.total_a_pagar:.2f}")
        self.lbl_total.setObjectName("paymentTotalAmount")
        self.lbl_total.setAlignment(Qt.AlignCenter)
        hdr_lay.addWidget(lbl_caption)
        hdr_lay.addWidget(self.lbl_total)
        layout.addWidget(header)

        # ── Form ────────────────────────────────────────────────────────────
        form_layout = QFormLayout()
        form_layout.setSpacing(8)
        form_layout.setContentsMargins(0, 4, 0, 4)
        form_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.cmb_forma_pago = QComboBox()
        self.cmb_forma_pago.addItems(["Efectivo", "Tarjeta", "Transferencia", "Crédito", "Pago Mixto", "Mercado Pago"])
        self.cmb_forma_pago.setObjectName("paymentCombo")
        self.cmb_forma_pago.setMinimumHeight(32)
        form_layout.addRow("Forma de pago:", self.cmb_forma_pago)

        self.txt_recibido = QDoubleSpinBox()
        self.txt_recibido.setRange(0.00, 99999.00)
        self.txt_recibido.setDecimals(2)
        self.txt_recibido.setValue(self.total_a_pagar)
        self.txt_recibido.setSingleStep(10.0)
        self.txt_recibido.setPrefix("$ ")
        self.txt_recibido.setMinimumHeight(36)
        self.txt_recibido.setObjectName("paymentSpinbox")
        self.txt_recibido.lineEdit().setReadOnly(False)
        form_layout.addRow("Monto recibido:", self.txt_recibido)
        
        self.lbl_cambio = QLabel("Cambio: $0.00")
        self.lbl_cambio.setObjectName("paymentChange")
        form_layout.addRow("", self.lbl_cambio)

        # v13.4 Fase 2: Sección de canje de puntos
        self._loyalty_widget = QWidget()
        _loy_lay = QVBoxLayout(self._loyalty_widget)
        _loy_lay.setContentsMargins(0, 0, 0, 0)
        _loy_lay.setSpacing(3)
        pts = self._loyalty.get("puntos_disponibles", self._loyalty.get("puntos", 0))
        valor = self._loyalty.get("descuento_maximo", self._loyalty.get("valor_canje", 0))
        puede = self._loyalty.get("enabled", self._loyalty.get("puede_canjear", False))

        _loy_header = QHBoxLayout()
        self._lbl_puntos = QLabel(f"⭐ {pts} puntos disponibles (=${valor:.2f})")
        self._lbl_puntos.setProperty("class", "text-bold")
        _loy_header.addWidget(self._lbl_puntos)
        _loy_lay.addLayout(_loy_header)

        _loy_row = QHBoxLayout()
        self._chk_canjear = QCheckBox("Usar puntos")
        self._chk_canjear.setEnabled(puede)
        self._chk_canjear.toggled.connect(self._toggle_canje)
        self._spin_puntos = QSpinBox()
        self._spin_puntos.setRange(0, pts)
        self._spin_puntos.setValue(pts)
        self._spin_puntos.setEnabled(False)
        self._spin_puntos.setSuffix(" pts")
        self._spin_puntos.valueChanged.connect(self._recalcular_canje)
        self._lbl_desc_puntos = QLabel("")
        self._lbl_desc_puntos.setProperty("class", "text-success")
        _loy_row.addWidget(self._chk_canjear)
        _loy_row.addWidget(self._spin_puntos)
        _loy_row.addWidget(self._lbl_desc_puntos)
        _loy_lay.addLayout(_loy_row)

        if not puede and pts > 0:
            mn = self._loyalty.get("min_puntos_canje", 100)
            _loy_lay.addWidget(QLabel(f"Mínimo {mn} puntos para canjear"))
        self._loyalty_widget.setVisible(pts > 0)
        form_layout.addRow("", self._loyalty_widget)
        
        self.txt_saldo_credito = QDoubleSpinBox()
        self.txt_saldo_credito.setRange(0.00, 99999.00)
        self.txt_saldo_credito.setDecimals(2)
        self.txt_saldo_credito.setValue(self.total_a_pagar)
        self.txt_saldo_credito.setProperty("class", "payment-spinbox")
        form_layout.addRow("Saldo Adeudado:", self.txt_saldo_credito)
        self.txt_saldo_credito.hide()

        # Pago mixto (efectivo + tarjeta)
        self._mixto_widget = QWidget()
        _ml = QHBoxLayout(self._mixto_widget)
        _ml.setContentsMargins(0, 0, 0, 0)
        _ml.addWidget(QLabel("Efectivo:"))
        self.spin_efectivo_mixto = QDoubleSpinBox()
        self.spin_efectivo_mixto.setRange(0, 99999); self.spin_efectivo_mixto.setDecimals(2)
        self.spin_efectivo_mixto.valueChanged.connect(self._recalcular_mixto)
        _ml.addWidget(self.spin_efectivo_mixto)
        _ml.addWidget(QLabel("Tarjeta:"))
        self.spin_tarjeta_mixto = QDoubleSpinBox()
        self.spin_tarjeta_mixto.setRange(0, 99999); self.spin_tarjeta_mixto.setDecimals(2)
        self.spin_tarjeta_mixto.valueChanged.connect(self._recalcular_mixto)
        _ml.addWidget(self.spin_tarjeta_mixto)
        self.lbl_mixto_diff = QLabel("")
        self.lbl_mixto_diff.setProperty("class", "text-danger caption")
        _ml.addWidget(self.lbl_mixto_diff)
        self._mixto_widget.hide()
        form_layout.addRow("", self._mixto_widget)
        
        layout.addLayout(form_layout)
        layout.addStretch(1)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setObjectName("paymentCancelBtn")
        self.btn_cancelar.setMinimumHeight(36)
        self.btn_aceptar = QPushButton("💰 Confirmar Pago")
        self.btn_aceptar.setObjectName("paymentConfirmBtn")
        self.btn_aceptar.setMinimumHeight(40)
        btn_layout.addWidget(self.btn_cancelar)
        btn_layout.addWidget(self.btn_aceptar, 2)
        layout.addLayout(btn_layout)

        self.calcular_cambio()
        
    def conectar_eventos(self):
        self.txt_recibido.valueChanged.connect(self.calcular_cambio)
        self.cmb_forma_pago.currentTextChanged.connect(self.cambiar_forma_pago)
        self.btn_aceptar.clicked.connect(self.accept)
        self.btn_cancelar.clicked.connect(self.reject)

    def showEvent(self, event):
        """v13.4: Auto-focus y select all en campo de efectivo."""
        super().showEvent(event)
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(50, lambda: (
            self.txt_recibido.setFocus(),
            self.txt_recibido.selectAll()))
        
    def cambiar_forma_pago(self, forma_pago):
        try:
            from core.services.sales.payment_policy import PaymentPolicy
            self.forma_pago = PaymentPolicy.normalize_payment_method(forma_pago)
        except Exception:
            self.forma_pago = forma_pago
        forma_pago = self.forma_pago
        if forma_pago == "Efectivo":
            self.txt_recibido.setEnabled(True)
            self.txt_recibido.setValue(self.total_a_pagar)
            self.lbl_cambio.show()
            self.txt_saldo_credito.hide()
        elif forma_pago == "Crédito":
            self.txt_recibido.setEnabled(False)
            self.lbl_cambio.hide()
            self.txt_saldo_credito.show()
            self.txt_saldo_credito.setValue(self.total_a_pagar)
        elif forma_pago == "Mercado Pago":
            self.txt_recibido.setEnabled(False)
            self.txt_recibido.setValue(self.total_a_pagar)
            self.lbl_cambio.hide()
            self.txt_saldo_credito.hide()
            self._mixto_widget.hide()
            # Mostrar info: se generará link al confirmar
            self.lbl_mp_info = getattr(self, 'lbl_mp_info', None)
            if not self.lbl_mp_info:
                from PyQt5.QtWidgets import QLabel
                self.lbl_mp_info = QLabel("🔗 Se generará link de pago al confirmar")
                self.lbl_mp_info.setProperty("class", "text-info caption-bold")
                self.layout().insertWidget(self.layout().count()-1, self.lbl_mp_info)
            self.lbl_mp_info.show()
        elif forma_pago == "Pago Mixto":
            self.txt_recibido.setEnabled(False)
            self.lbl_cambio.hide()
            self.txt_saldo_credito.hide()
            self._mixto_widget.show()
            self.spin_efectivo_mixto.setValue(round(self.total_a_pagar * 0.5, 2))
            self.spin_tarjeta_mixto.setValue(round(self.total_a_pagar * 0.5, 2))
        else:
            self.txt_recibido.setEnabled(False)
            self.txt_recibido.setValue(self.total_a_pagar)
            self.lbl_cambio.hide()
            self.txt_saldo_credito.hide()
            self._mixto_widget.hide()
        if hasattr(self,'lbl_mp_info') and self.lbl_mp_info and forma_pago != 'Mercado Pago':
            self.lbl_mp_info.hide()
        self.calcular_cambio()

    def calcular_cambio(self):
        self.efectivo_recibido = self.txt_recibido.value()
        try:
            from core.services.sales.payment_policy import PaymentPolicy
            validation = PaymentPolicy.validate_payment(
                total=self.total_a_pagar,
                method=self.forma_pago,
                amount_paid=self.efectivo_recibido,
                cash=self.spin_efectivo_mixto.value() if hasattr(self, "spin_efectivo_mixto") else 0.0,
                card=self.spin_tarjeta_mixto.value() if hasattr(self, "spin_tarjeta_mixto") else 0.0,
            )
            self.cambio = float(validation.get("change", 0.0))
            ok = bool(validation.get("ok", True))
        except Exception:
            ok = True
            self.cambio = round(self.efectivo_recibido - self.total_a_pagar, 2) if self.forma_pago == "Efectivo" else 0.0
        if self.forma_pago == "Efectivo":
            self.lbl_cambio.setText(f"Cambio: ${self.cambio:.2f}")
            if not ok or self.cambio < 0:
                self.btn_aceptar.setEnabled(False)
                self.lbl_cambio.setProperty("class", "payment-change-negative")
            else:
                self.btn_aceptar.setEnabled(True)
                self.lbl_cambio.setProperty("class", "payment-change")
        else:
            self.efectivo_recibido = self.total_a_pagar
            self.cambio = 0.0
            self.btn_aceptar.setEnabled(True)

    def _recalcular_mixto(self):
        if self.forma_pago != "Pago Mixto":
            return
        ef = self.spin_efectivo_mixto.value()
        ta = self.spin_tarjeta_mixto.value()
        try:
            from core.services.sales.payment_policy import PaymentPolicy
            v = PaymentPolicy.validate_mixed_payment(self.total_a_pagar, ef, ta)
            diff = float(v.get("diff", 0.0))
        except Exception:
            total = ef + ta
            diff = round(total - self.total_a_pagar, 2)
        if abs(diff) < 0.01:
            self.lbl_mixto_diff.setText("✅ Cuadra")
            self.lbl_mixto_diff.setProperty("class", "text-success caption")
            self.btn_aceptar.setEnabled(True)
        elif diff > 0:
            self.lbl_mixto_diff.setText(f"Sobran ${diff:.2f}")
            self.lbl_mixto_diff.setProperty("class", "text-warning caption")
            self.btn_aceptar.setEnabled(True)
        else:
            self.lbl_mixto_diff.setText(f"Faltan ${abs(diff):.2f}")
            self.lbl_mixto_diff.setProperty("class", "text-danger caption")
            self.btn_aceptar.setEnabled(False)

    def _toggle_canje(self, checked: bool):
        """v13.4 Fase 0 hotfix: Activa/desactiva el canje de puntos de fidelidad."""
        if not hasattr(self, "_spin_puntos"):
            return
        self._spin_puntos.setEnabled(checked)
        if checked:
            self._recalcular_canje(self._spin_puntos.value())
        else:
            self.descuento_puntos = 0.0
            self.puntos_a_canjear = 0
            self.total_a_pagar = self.total_original
            self._lbl_desc_puntos.setText("")
            self.lbl_total.setText(f"Total a pagar: ${self.total_a_pagar:.2f}")
            if hasattr(self, "txt_recibido"):
                self.txt_recibido.setValue(self.total_a_pagar)
            self.calcular_cambio()

    def _recalcular_canje(self, value: int):
        """v13.4 Fase 0 hotfix: Recalcula descuento al modificar puntos a canjear."""
        if not hasattr(self, "_chk_canjear") or not self._chk_canjear.isChecked():
            return
        descuento = 0.0
        if callable(self._loyalty_preview_provider):
            try:
                preview = self._loyalty_preview_provider(value, self.total_original) or {}
                descuento = float(preview.get("descuento", 0.0))
            except Exception:
                descuento = 0.0
        else:
            descuento = 0.0
        descuento = min(round(descuento, 2), self.total_original)
        self.descuento_puntos = descuento
        self.puntos_a_canjear = value
        self.total_a_pagar = round(self.total_original - descuento, 2)
        self._lbl_desc_puntos.setText(f"-${descuento:.2f}")
        self.lbl_total.setText(f"Total a pagar: ${self.total_a_pagar:.2f}")
        if hasattr(self, "txt_recibido"):
            self.txt_recibido.setValue(self.total_a_pagar)
        self.calcular_cambio()

    def get_datos_pago(self) -> Dict[str, Any]:
        try:
            from core.services.sales.payment_policy import PaymentPolicy
            payload = PaymentPolicy.build_payment_breakdown(
                total=self.total_a_pagar,
                method=self.forma_pago,
                amount_paid=self.efectivo_recibido,
                cash=self.spin_efectivo_mixto.value() if self.forma_pago == "Pago Mixto" else 0.0,
                card=self.spin_tarjeta_mixto.value() if self.forma_pago == "Pago Mixto" else 0.0,
                saldo_credito=self.txt_saldo_credito.value() if self.forma_pago == "Crédito" else 0.0,
            )
        except Exception:
            payload = {
                "forma_pago": self.forma_pago,
                "total_pagado": self.total_a_pagar,
                "efectivo_recibido": self.efectivo_recibido,
                "monto_tarjeta_mixto": 0.0,
                "cambio": self.cambio,
                "saldo_credito": self.txt_saldo_credito.value() if self.forma_pago == "Crédito" else 0.0,
            }
        payload.update({
            "puntos_canjeados": self.puntos_a_canjear,
            "descuento_puntos": self.descuento_puntos,
        })
        return payload

