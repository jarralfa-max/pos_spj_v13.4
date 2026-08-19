"""SalesPosWorkspace (POS-19/POS-20) — the decomposed Sales/POS screen shell.

Structural equivalent of the master prompt's own "Regla Visual No
Negociable": exactly one top-level `QSplitter`, exactly two panels
(catalog left / checkout right), cashier bar on top — same structural rule
`tests/visual/golden/sales_pos/test_pos_preserves_two_panel_layout.py`
already enforces against the LEGACY `ModuloVentas`. This is a NEW, parallel
widget (see `docs/refactor/SALES-19_ui_decomposition.md` for why it is not
wired into the live app) — `tests/unit/test_sales_pos_workspace.py` is the
equivalent structural guardrail for this tree.

POS-20 "Validar teclado": unlike the legacy screen's F6-F12 badges
(confirmed decorative — no `QShortcut` exists anywhere for them, per
`docs/refactor/sales_pos_visual_contract.md` §4.1), this workspace is new
code with no inherited constraint to preserve that gap, so the shortcuts
here are real `QShortcut`s wired to the same handlers the buttons trigger.

POS-20 "Validar scanner": `CatalogPanel.code_scanned` (a barcode scanner is,
electrically, a very fast typist followed by Enter) routes through
`SalesPosPresenter.scan_code()` → SALES-12's `ScanCodeRouter` — the real,
previously-unwired consumer of that use case.
"""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QMessageBox, QShortcut, QSplitter, QVBoxLayout, QWidget

from frontend.desktop.modules.sales_pos.components.cashier_bar import CashierBar
from frontend.desktop.modules.sales_pos.components.catalog_panel import CatalogPanel
from frontend.desktop.modules.sales_pos.components.checkout_panel import CheckoutPanel
from frontend.desktop.modules.sales_pos.dialogs.discount_dialog import DiscountDialog
from frontend.desktop.modules.sales_pos.dialogs.payment_dialog import PaymentDialog
from frontend.desktop.modules.sales_pos.dialogs.quick_customer_dialog import QuickCustomerDialog


class SalesPosWorkspace(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("salesPosWorkspace")
        self._presenter = presenter
        self._sale_id: str | None = None
        self._sale_started = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.cashier_bar = CashierBar(presenter, self)
        root.addWidget(self.cashier_bar)

        self._splitter = QSplitter(self)
        self.catalog = CatalogPanel(presenter, self)
        self.catalog.product_selected.connect(self._on_product_selected)
        self.catalog.code_scanned.connect(self._on_code_scanned)
        self._splitter.addWidget(self.catalog)

        self.checkout = CheckoutPanel(presenter, self)
        self.checkout.customer_selected.connect(self._on_customer_selected)
        self.checkout.checkout_requested.connect(self._on_checkout_requested)
        self.checkout.suspend_requested.connect(self._on_suspend_requested)
        self.checkout.resume_requested.connect(self._on_resume_requested)
        self.checkout.cancel_requested.connect(self._on_cancel_requested)
        self.checkout.reprint_requested.connect(self._on_reprint_requested)
        self.checkout.invoice_requested.connect(self._on_invoice_requested)
        self._splitter.addWidget(self.checkout)

        self.checkout.customer.quick_create_button().clicked.connect(
            self._on_quick_create_customer)

        # POS-20 "Corregir proporciones": the catalog panel absorbs all
        # extra width at wider resolutions; the checkout panel stays at its
        # own bounded width (set on `CheckoutPanel` itself, 380-600px,
        # matching the legacy `panel_derecho` contract) — without an
        # explicit stretch factor a QSplitter grows both panels
        # proportionally regardless of their own max-width, which is what
        # produced the ~900px-wide checkout panel this fix replaces.
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 0)

        root.addWidget(self._splitter, stretch=1)

        self._wire_shortcuts()
        self.catalog.load_categories()

    def showEvent(self, event) -> None:
        """`interfaz/main_window.py::_conectar` constructs every module
        screen eagerly at app startup, before any user is authenticated
        (`session_context.user_id` is empty until login completes) — but
        this screen only becomes actually visible once the user navigates
        to POS, which can only happen post-login. Starting a sale eagerly in
        `__init__` (the original POS-22 wiring) crashed hard the first time
        this ran for real: `SalesPosPresenter.count_suspended()` requires an
        authenticated user and raises `SalesPermissionDeniedError` instead
        of degrading, so the whole module failed to load. Deferred here,
        gated on a real `current_user_id()`, and only attempted once."""
        super().showEvent(event)
        if not self._sale_started and self._presenter.current_user_id():
            self._sale_started = True
            self._start_new_sale()

    def _wire_shortcuts(self) -> None:
        """POS-20 "Validar teclado": real shortcuts, each firing the exact
        same handler its matching button already does — never a second,
        divergent code path."""
        bindings = {
            "F6": self._on_suspend_requested,
            "F7": self._on_resume_requested,
            "F8": self._on_cancel_requested,
            "F9": self._on_checkout_requested,
            "F10": self.checkout.actions.return_requested.emit,
            "F11": self.checkout.actions.invoice_requested.emit,
            "F12": self.checkout.actions.reprint_requested.emit,
        }
        self._shortcuts = [
            QShortcut(QKeySequence(key), self, activated=handler)
            for key, handler in bindings.items()
        ]

    # ── sale lifecycle ───────────────────────────────────────────────────

    def _start_new_sale(self) -> None:
        result = self._presenter.start_sale()
        self._sale_id = result.entity_id if result.success else None
        self._refresh()

    def _refresh(self) -> None:
        sale = self._presenter.get_sale(self._sale_id) if self._sale_id else None
        self.checkout.render_sale(sale)
        self.checkout.refresh_suspended_count()
        self.cashier_bar.refresh_suspended_count()
        self.catalog.refresh()

    # ── event handlers (each delegates to the presenter, never touches
    #    the backend directly) ───────────────────────────────────────────

    def _on_product_selected(self, product_id: str) -> None:
        if not self._sale_id:
            return
        products = {p.product_id: p for p in self._presenter.catalog_search()}
        product = products.get(product_id)
        if product is None:
            return
        self._presenter.add_line(
            sale_id=self._sale_id, product_id=product_id, quantity=_ONE,
            unit_price=product.effective_price,
            product_snapshot={"name": product.name, "sku": product.sku})
        self._refresh()

    def _on_customer_selected(self, customer_id: str) -> None:
        if not self._sale_id:
            return
        self._presenter.assign_customer(sale_id=self._sale_id, customer_id=customer_id)
        self._refresh()

    def _on_quick_create_customer(self) -> None:
        dialog = QuickCustomerDialog(self._presenter, self)
        if dialog.exec_() and dialog.customer_id and self._sale_id:
            self._presenter.assign_customer(sale_id=self._sale_id, customer_id=dialog.customer_id)
            self._refresh()

    def _on_checkout_requested(self) -> None:
        """POS-22 prerequisite: real payment collection via `PaymentDialog`
        instead of calling `checkout_sale` directly — SALES-13/14's real
        `SalePaymentPolicy.ensure_fully_paid` gate rejects a checkout with
        zero recorded payments, which is what this handler used to attempt
        every time before the dialog existed."""
        if not self._sale_id:
            return
        sale = self._presenter.get_sale(self._sale_id)
        if sale is None:
            return
        dialog = PaymentDialog(self._presenter, sale_id=self._sale_id, total_due=sale.total, parent=self)
        if dialog.exec_() and dialog.completed:
            QMessageBox.information(self, "Venta completada", "Venta finalizada correctamente.")
            self._start_new_sale()

    def _on_suspend_requested(self) -> None:
        if not self._sale_id:
            return
        result = self._presenter.suspend_sale(sale_id=self._sale_id)
        if result.success:
            self._start_new_sale()
        else:
            QMessageBox.warning(self, "No se pudo suspender", result.message)

    def _on_resume_requested(self) -> None:
        suspended = self._presenter.list_suspended()
        if not suspended:
            QMessageBox.information(self, "Sin ventas suspendidas", "No hay ventas suspendidas.")
            return
        result = self._presenter.resume_sale(sale_id=suspended[0].id)
        if result.success:
            self._sale_id = suspended[0].id
            self._refresh()

    def _on_cancel_requested(self) -> None:
        if not self._sale_id:
            return
        result = self._presenter.cancel_sale(sale_id=self._sale_id, reason="Cancelada por cajero")
        if result.success:
            self._start_new_sale()
        else:
            QMessageBox.warning(self, "No se pudo cancelar", result.message)

    def _on_code_scanned(self, code: str) -> None:
        """POS-20 "Validar scanner". `context="AUTO"` mirrors
        `ScanCodeRouter`'s own real behavior (SALES-12): tries a product
        match first, falls back to a loyalty/customer card. A failed scan
        surfaces the real `ScanCodeNotResolvedError` message, never a
        silent no-op."""
        if not self._sale_id:
            return
        result = self._presenter.scan_code(sale_id=self._sale_id, code=code, context="AUTO")
        self.catalog.clear_search()
        if result.success:
            self._refresh()
        else:
            QMessageBox.warning(self, "Código no reconocido", result.message)

    def _on_reprint_requested(self) -> None:
        if not self._sale_id:
            return
        cajero_nombre = self._presenter.current_user_id()
        result = self._presenter.reprint_receipt(sale_id=self._sale_id, cajero_nombre=cajero_nombre)
        if not result.success:
            QMessageBox.warning(self, "No se pudo reimprimir", result.message)

    def _on_invoice_requested(self) -> None:
        if not self._sale_id:
            return
        result = self._presenter.request_invoice(sale_id=self._sale_id)
        if result.success:
            QMessageBox.information(self, "Factura solicitada", result.message)
        else:
            QMessageBox.warning(self, "No se pudo solicitar factura", result.message)

    def refresh_products(self) -> None:
        """POS-22 prerequisite: hot-refresh contract (`core/events/
        catalog_events.py::fan_out_products_changed`) — the legacy screen
        implemented this (`Remediación B`); this new tree never did, so a
        product created/edited elsewhere while this screen was open never
        reached the catalog grid until reopened. Reuses `CatalogPanel`'s own
        real requery, no separate logic."""
        self.catalog.refresh()

    def refresh_branches(self) -> None:
        """Same hot-refresh contract, branch side — see `refresh_products`."""
        self.catalog.refresh()

    def aplicar_contexto(self, context: dict) -> None:
        """POS-22 prerequisite — receiving end of the real `NavigationIntent`
        (route `"sales.new"`, `interfaz/main_window.py::_handle_navigation_intent`)
        coming from the Customer 360 profile's "Nueva venta" action, mirroring
        `modulos.ventas.ModuloVentas.aplicar_contexto`'s real behavior but
        simpler: `context["customer_id"]` is already a Customer Master id, and
        `AssignCustomerToSaleUseCase` (SALES-10) accepts that id directly — no
        legacy `clientes` bridge lookup needed, unlike the legacy screen which
        operates on the bridged legacy id instead."""
        customer_id = str((context or {}).get("customer_id") or "").strip()
        if not customer_id or not self._sale_id:
            return
        result = self._presenter.assign_customer(sale_id=self._sale_id, customer_id=customer_id)
        if result.success:
            self._refresh()

    def open_discount_dialog(self) -> None:
        if not self._sale_id:
            return
        dialog = DiscountDialog(self._presenter, sale_id=self._sale_id, parent=self)
        if dialog.exec_() and dialog.applied:
            self._refresh()


_ONE = Decimal("1")
