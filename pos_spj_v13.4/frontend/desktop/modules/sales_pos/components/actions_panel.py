"""ActionsPanel (POS-19) — structural equivalent of the legacy
`group_acciones`/`group_utilidad` (Cobrar dominant + Suspender/Reanudar/
Cancelar + Devolución/Factura/Reimpr, `docs/refactor/
sales_pos_layout_inventory.md` §1) — same button VARIANTS as the legacy
contract (Cobrar=success, Suspender=warning, Reanudar=primary,
Cancelar=danger, confirmed in `sales_pos_visual_contract.md`), each wired to
the real use case its label names (SALES-9/14/15/16/17/18) instead of the
legacy screen's own inline handlers.

F6-F12 badges are intentionally NOT painted here — the visual contract
(§4.1) confirms those are purely decorative in the legacy screen (no real
`QShortcut` exists anywhere for them); this component does not reproduce a
decoration with no real behavior behind it.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout

from frontend.desktop.components import (
    create_danger_button,
    create_primary_button,
    create_success_button,
    create_warning_button,
)


class ActionsPanel(QFrame):
    checkout_requested = pyqtSignal()
    suspend_requested = pyqtSignal()
    resume_requested = pyqtSignal()
    cancel_requested = pyqtSignal()
    return_requested = pyqtSignal()
    invoice_requested = pyqtSignal()
    reprint_requested = pyqtSignal()

    def __init__(self, capabilities, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("posCobrarFrame")

        root = QVBoxLayout(self)

        self.btn_cobrar = create_success_button(self, "💳 COBRAR $0.00")
        self.btn_cobrar.setObjectName("btnCobrarPOS")
        self.btn_cobrar.setEnabled(capabilities.sale_complete)
        self.btn_cobrar.clicked.connect(self.checkout_requested)
        root.addWidget(self.btn_cobrar)

        secondary = QHBoxLayout()
        self.btn_suspender = create_warning_button(self, "⏸ Suspender")
        self.btn_suspender.setEnabled(capabilities.sale_suspend)
        self.btn_suspender.clicked.connect(self.suspend_requested)
        secondary.addWidget(self.btn_suspender)

        self.btn_reanudar = create_primary_button(self, "▶ Reanudar (0)")
        self.btn_reanudar.setEnabled(capabilities.sale_resume)
        self.btn_reanudar.clicked.connect(self.resume_requested)
        secondary.addWidget(self.btn_reanudar)

        self.btn_cancelar = create_danger_button(self, "✕ Cancelar")
        self.btn_cancelar.setEnabled(capabilities.sale_cancel)
        self.btn_cancelar.clicked.connect(self.cancel_requested)
        secondary.addWidget(self.btn_cancelar)
        root.addLayout(secondary)

        utility = QHBoxLayout()
        self.btn_devolucion = create_danger_button(self, "↩ Devolución")
        self.btn_devolucion.setObjectName("posUtilBtn")
        self.btn_devolucion.setEnabled(capabilities.sale_return)
        self.btn_devolucion.clicked.connect(self.return_requested)
        utility.addWidget(self.btn_devolucion)

        self.btn_factura = create_primary_button(self, "🧾 Factura")
        self.btn_factura.setObjectName("posUtilBtn")
        self.btn_factura.setEnabled(capabilities.invoice_request)
        self.btn_factura.clicked.connect(self.invoice_requested)
        utility.addWidget(self.btn_factura)

        self.btn_reimprimir = create_primary_button(self, "🖨️ Reimpr.")
        self.btn_reimprimir.setObjectName("posUtilBtn")
        self.btn_reimprimir.setEnabled(capabilities.receipt_reprint)
        self.btn_reimprimir.clicked.connect(self.reprint_requested)
        utility.addWidget(self.btn_reimprimir)
        root.addLayout(utility)

    def set_total(self, total_text: str) -> None:
        self.btn_cobrar.setText(f"💳 COBRAR {total_text}")

    def set_suspended_count(self, count: int) -> None:
        self.btn_reanudar.setText(f"▶ Reanudar ({count})")
