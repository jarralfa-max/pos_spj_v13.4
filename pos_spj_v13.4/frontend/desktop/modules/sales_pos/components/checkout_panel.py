"""CheckoutPanel — panel derecho del POS.

Ensambla Carrito → Cliente → Totales → Acciones **en ese orden**, el orden
REAL del POS documentado en `docs/refactor/sales_pos_visual_contract.md` §1
("Carrito → Cliente → Totales → Descuentos rápidos → Cobrar → Suspender/
Reanudar/Cancelar → Devolución/Factura/Reimpr."). SALES-1 ya resolvió la
tensión con la lista abstracta del prompt maestro (cliente antes que carrito)
a favor del orden real; se conserva.

Sólo re-emite intenciones; ninguna regla vive aquí.
"""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.modules.sales_pos.components.actions_panel import ActionsPanel
from frontend.desktop.modules.sales_pos.components.cart_table import CartTable
from frontend.desktop.modules.sales_pos.components.customer_panel import CustomerPanel
from frontend.desktop.modules.sales_pos.components.totals_card import TotalsCard


class CheckoutPanel(QWidget):
    line_selected = pyqtSignal(str)
    line_quantity_requested = pyqtSignal(str)
    line_remove_requested = pyqtSignal(str)
    customer_selected = pyqtSignal(str)
    customer_clear_requested = pyqtSignal()
    checkout_requested = pyqtSignal()
    suspend_requested = pyqtSignal()
    resume_requested = pyqtSignal()
    cancel_requested = pyqtSignal()
    return_requested = pyqtSignal()
    invoice_requested = pyqtSignal()
    reprint_requested = pyqtSignal()
    discount_requested = pyqtSignal()
    quick_discount_requested = pyqtSignal(object)  # Decimal: porcentaje

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("posCheckoutPanel")
        self._presenter = presenter
        capabilities = presenter.capabilities()

        # Barra lateral de ancho acotado (`sales_pos_layout_inventory.md` §1:
        # `panel_derecho`, 380-600 px): el catálogo absorbe el ancho extra.
        self.setMinimumWidth(380)
        self.setMaximumWidth(600)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.cart = CartTable(
            self, can_edit=capabilities.line_update or capabilities.line_remove)
        self.cart.line_selected.connect(self.line_selected)
        self.cart.quantity_requested.connect(self.line_quantity_requested)
        self.cart.remove_requested.connect(self.line_remove_requested)
        self.cart.clear_requested.connect(self.cancel_requested)
        root.addWidget(self.cart, stretch=1)

        self.customer = CustomerPanel(presenter, self)
        self.customer.customer_selected.connect(self.customer_selected)
        self.customer.clear_requested.connect(self.customer_clear_requested)
        root.addWidget(self.customer)

        self.totals = TotalsCard(self)
        root.addWidget(self.totals)

        self.actions = ActionsPanel(capabilities, self)
        self.actions.checkout_requested.connect(self.checkout_requested)
        self.actions.suspend_requested.connect(self.suspend_requested)
        self.actions.resume_requested.connect(self.resume_requested)
        self.actions.cancel_requested.connect(self.cancel_requested)
        self.actions.return_requested.connect(self.return_requested)
        self.actions.invoice_requested.connect(self.invoice_requested)
        self.actions.reprint_requested.connect(self.reprint_requested)
        self.actions.discount_requested.connect(self.discount_requested)
        self.actions.quick_discount_requested.connect(self.quick_discount_requested)
        root.addWidget(self.actions)

    def render_sale(self, sale, customer=None) -> None:
        if sale is None:
            self.cart.set_lines([])
            self.totals.set_totals(_ZeroTotals())
            self.actions.set_total("$0.00")
            self.customer.set_customer(None)
            return
        self.cart.set_lines(sale.lines)
        self.totals.set_totals(sale)
        self.actions.set_total(f"${sale.total:,.2f}")
        self.customer.set_customer(customer)

    def refresh_suspended_count(self) -> None:
        self.actions.set_suspended_count(self._presenter.count_suspended())


class _ZeroTotals:
    gross_subtotal = Decimal("0")
    discount_total = Decimal("0")
    loyalty_total = Decimal("0")
    tax_total = Decimal("0")
    total = Decimal("0")
