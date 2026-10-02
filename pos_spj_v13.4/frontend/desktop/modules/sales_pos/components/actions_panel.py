"""ActionsPanel — el bloque inferior del panel de venta, en el orden del
contrato visual (`docs/refactor/sales_pos_visual_contract.md` §1):

    Descuentos rápidos (5 % 10 % 15 % 20 % Personalizado)
    COBRAR $total                                  ← acción dominante (F9)
    Suspender (F6) · Reanudar (n) (F7) · Cancelar (F8)
    Devolución (F10) · Factura (F11) · Reimprimir (F12)

Re-auditoría POS (2026-10-01), medido con captura sobre una copia de la base
real: COBRAR era el botón MENOS visible de la pantalla. El sistema de diseño
redujo las variantes "success"/"warning" a "secondary" (gris), así que COBRAR
salía gris mientras Reanudar/Factura/Reimprimir salían en el color primario.
Ahora COBRAR es la única acción primaria con énfasis dominante; las demás son
secundarias y Cancelar es la única destructiva. Los atajos se pintan en el
texto (§54-55: "atajos visibles") y los iconos salen del catálogo del sistema
de diseño, no de emojis (§57).

Los descuentos rápidos estaban en el contrato y no existían: había un único
"% Descuento". El porcentaje viaja al caso de uso; el monto lo calcula el
dominio (`SaleDiscountPolicy.amount_for_percent`), no este widget.
"""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout

from frontend.desktop.components import (
    IconProvider,
    Icons,
    create_danger_button,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.themes.tokens import Spacing

#: Botones rápidos del contrato visual (§25).
QUICK_DISCOUNT_PERCENTS = (Decimal("5"), Decimal("10"), Decimal("15"), Decimal("20"))


class ActionsPanel(QFrame):
    checkout_requested = pyqtSignal()
    suspend_requested = pyqtSignal()
    resume_requested = pyqtSignal()
    cancel_requested = pyqtSignal()
    return_requested = pyqtSignal()
    invoice_requested = pyqtSignal()
    reprint_requested = pyqtSignal()
    discount_requested = pyqtSignal()
    quick_discount_requested = pyqtSignal(object)  # Decimal: porcentaje

    def __init__(self, capabilities, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("posCobrarFrame")

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        root.setSpacing(Spacing.SM)

        discount_bar = QHBoxLayout()
        discount_bar.setSpacing(Spacing.XS)
        self.quick_discount_buttons = []
        for percent in QUICK_DISCOUNT_PERCENTS:
            button = create_secondary_button(
                self, f"{percent}%", tooltip=f"Descuento de {percent}% a toda la venta")
            button.setObjectName("posQuickDiscount")
            button.setEnabled(capabilities.discount_apply)
            button.clicked.connect(
                lambda _checked=False, p=percent: self.quick_discount_requested.emit(p))
            discount_bar.addWidget(button)
            self.quick_discount_buttons.append(button)
        self.btn_descuento = create_secondary_button(
            self, "Personalizado (F5)", tooltip="Descuento por monto, con motivo (F5)")
        self.btn_descuento.setObjectName("posUtilBtn")
        self.btn_descuento.setEnabled(capabilities.discount_apply)
        self.btn_descuento.clicked.connect(self.discount_requested)
        discount_bar.addWidget(self.btn_descuento, stretch=1)
        root.addLayout(discount_bar)

        self.btn_cobrar = create_primary_button(
            self, "COBRAR $0.00   (F9)", tooltip="Cobrar la venta (F9)")
        self.btn_cobrar.setObjectName("btnCobrarPOS")
        self.btn_cobrar.setProperty("emphasis", "dominant")
        IconProvider.bind(self.btn_cobrar, Icons.CASH, size=24)
        self.btn_cobrar.setEnabled(capabilities.sale_complete)
        self.btn_cobrar.clicked.connect(self.checkout_requested)
        root.addWidget(self.btn_cobrar)

        secondary = QHBoxLayout()
        secondary.setSpacing(Spacing.XS)
        self.btn_suspender = create_secondary_button(
            self, "Suspender (F6)", tooltip="Guardar la venta para continuarla después (F6)")
        IconProvider.bind(self.btn_suspender, Icons.PENDING)
        self.btn_suspender.setEnabled(capabilities.sale_suspend)
        self.btn_suspender.clicked.connect(self.suspend_requested)
        secondary.addWidget(self.btn_suspender)

        self.btn_reanudar = create_secondary_button(
            self, "Reanudar (0) (F7)", tooltip="Continuar una venta suspendida (F7)")
        IconProvider.bind(self.btn_reanudar, Icons.REDO)
        self.btn_reanudar.setEnabled(capabilities.sale_resume)
        self.btn_reanudar.clicked.connect(self.resume_requested)
        secondary.addWidget(self.btn_reanudar)

        self.btn_cancelar = create_danger_button(
            self, "Cancelar (F8)", tooltip="Cancelar la venta en curso; pide motivo (F8)")
        IconProvider.bind(self.btn_cancelar, Icons.CLOSE)
        self.btn_cancelar.setEnabled(capabilities.sale_cancel)
        self.btn_cancelar.clicked.connect(self.cancel_requested)
        secondary.addWidget(self.btn_cancelar)
        root.addLayout(secondary)

        utility = QHBoxLayout()
        utility.setSpacing(Spacing.XS)
        self.btn_devolucion = create_secondary_button(
            self, "Devolución (F10)", tooltip="Devolver productos de una venta cobrada (F10)")
        self.btn_devolucion.setObjectName("posUtilBtn")
        IconProvider.bind(self.btn_devolucion, Icons.RETURN)
        self.btn_devolucion.setEnabled(capabilities.sale_return)
        self.btn_devolucion.clicked.connect(self.return_requested)
        utility.addWidget(self.btn_devolucion)

        self.btn_factura = create_secondary_button(
            self, "Factura (F11)", tooltip="Solicitar la factura de una venta cobrada (F11)")
        self.btn_factura.setObjectName("posUtilBtn")
        IconProvider.bind(self.btn_factura, Icons.DOCUMENT)
        self.btn_factura.setEnabled(capabilities.invoice_request)
        self.btn_factura.clicked.connect(self.invoice_requested)
        utility.addWidget(self.btn_factura)

        self.btn_reimprimir = create_secondary_button(
            self, "Reimprimir (F12)", tooltip="Reimprimir el ticket de una venta cobrada (F12)")
        self.btn_reimprimir.setObjectName("posUtilBtn")
        IconProvider.bind(self.btn_reimprimir, Icons.PRINT)
        self.btn_reimprimir.setEnabled(capabilities.receipt_reprint)
        self.btn_reimprimir.clicked.connect(self.reprint_requested)
        utility.addWidget(self.btn_reimprimir)
        root.addLayout(utility)

    def set_total(self, total_text: str) -> None:
        self.btn_cobrar.setText(f"COBRAR {total_text}   (F9)")

    def set_suspended_count(self, count: int) -> None:
        self.btn_reanudar.setText(f"Reanudar ({count}) (F7)")
