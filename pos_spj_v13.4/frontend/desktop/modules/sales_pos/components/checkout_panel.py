"""CheckoutPanel (POS-19) — right panel of the Sales/POS screen.

Assembles Cart → Customer → Totals → Actions **in that exact order** —
matching the REAL legacy vertical order documented in `docs/refactor/
sales_pos_visual_contract.md` (§1: "Carrito → Cliente → Totales →
Descuentos rápidos → Cobrar → Suspender/Reanudar/Cancelar → Devolución/
Factura/Reimpr."), not the master prompt's own §1 bullet list, which
implies customer before cart — SALES-1 already reconciled this exact
tension toward "real order wins over the prompt's abstract list," and this
component keeps that precedent rather than re-opening it.
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
    customer_selected = pyqtSignal(str)
    checkout_requested = pyqtSignal()
    suspend_requested = pyqtSignal()
    resume_requested = pyqtSignal()
    cancel_requested = pyqtSignal()
    return_requested = pyqtSignal()
    invoice_requested = pyqtSignal()
    reprint_requested = pyqtSignal()

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("posCheckoutPanel")
        self._presenter = presenter
        capabilities = presenter.capabilities()

        # POS-20 "Corregir proporciones": the legacy checkout panel is a
        # bounded-width sidebar (`docs/refactor/sales_pos_layout_inventory.md`
        # §1: `panel_derecho`, minimumWidth=380/maximumWidth=600) — without
        # this, an unconstrained QSplitter divides roughly 50/50, which at
        # 1920x1080 left the checkout panel ~900px wide (empirically
        # measured before this fix). The catalog/product grid is the panel
        # that should get the majority of extra width, matching real POS UX
        # and the legacy contract.
        self.setMinimumWidth(380)
        self.setMaximumWidth(600)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.cart = CartTable(self)
        self.cart.line_selected.connect(self.line_selected)
        root.addWidget(self.cart, stretch=1)

        self.customer = CustomerPanel(presenter, self)
        self.customer.customer_selected.connect(self.customer_selected)
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
        root.addWidget(self.actions)

    def render_sale(self, sale) -> None:
        if sale is None:
            self.cart.set_lines([])
            self.totals.set_totals(_ZeroTotals())
            self.actions.set_total("$0.00")
            self.customer.set_customer(None)
            return
        self.cart.set_lines(sale.lines)
        self.totals.set_totals(sale)
        self.actions.set_total(f"${sale.total:.2f}")

    def refresh_suspended_count(self) -> None:
        self.actions.set_suspended_count(self._presenter.count_suspended())


class _ZeroTotals:
    gross_subtotal = Decimal("0")
    discount_total = Decimal("0")
    loyalty_total = Decimal("0")
    tax_total = Decimal("0")
    total = Decimal("0")
