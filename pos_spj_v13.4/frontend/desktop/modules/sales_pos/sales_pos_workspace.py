"""SalesPosWorkspace — la pantalla del Punto de Venta.

Contrato visual NO negociable (prompt maestro §1, `docs/refactor/
sales_pos_visual_contract.md`): barra del cajero arriba y UN `QSplitter` con
DOS paneles — catálogo a la izquierda, venta a la derecha. Los atajos F5-F12
son `QShortcut` reales que disparan el MISMO manejador que su botón.

La pantalla captura intenciones y presenta estado (§3); cada acción la decide
un caso de uso a través de `SalesPosPresenter`.

Re-auditoría POS (2026-10-01) — lo que esta pantalla NO hacía, medido sobre una
copia de la base real:

* agregar un producto por kilo sumaba "1" sin pedir el peso (los 11 productos
  de la base se venden por KG); ahora pide el peso (`WeightCaptureDialog`);
* el carrito no permitía corregir ni quitar una línea;
* Devolución/F10 no tenía manejador;
* Reimprimir/F12 y Factura/F11 actuaban sobre la venta NUEVA, vacía;
* Reanudar tomaba siempre la primera suspendida; Cancelar no confirmaba y su
  motivo era fijo;
* tras cobrar no se imprimía ticket ni se decía el folio ni el cambio;
* el cliente asignado no se mostraba.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QMessageBox, QShortcut, QSplitter, QVBoxLayout, QWidget

from frontend.desktop.modules.sales_pos.components.cashier_bar import CashierBar
from frontend.desktop.modules.sales_pos.components.catalog_panel import CatalogPanel
from frontend.desktop.modules.sales_pos.components.checkout_panel import CheckoutPanel
from frontend.desktop.modules.sales_pos.customer_display_window import (
    CustomerDisplayWindow,
    QtCustomerDisplayGateway,
)
from frontend.desktop.modules.sales_pos.dialogs.cancel_sale_dialog import CancelSaleDialog
from frontend.desktop.modules.sales_pos.dialogs.discount_dialog import DiscountDialog
from frontend.desktop.modules.sales_pos.dialogs.invoice_request_dialog import InvoiceRequestDialog
from frontend.desktop.modules.sales_pos.dialogs.payment_dialog import PaymentDialog
from frontend.desktop.modules.sales_pos.dialogs.quantity_dialog import QuantityDialog
from frontend.desktop.modules.sales_pos.dialogs.quick_customer_dialog import QuickCustomerDialog
from frontend.desktop.modules.sales_pos.dialogs.receipt_options_dialog import (
    PostedSalePickerDialog,
    folio_of,
)
from frontend.desktop.modules.sales_pos.dialogs.coupon_dialog import CouponDialog
from frontend.desktop.modules.sales_pos.dialogs.prepaid_voucher_dialog import PrepaidVoucherDialog
from frontend.desktop.modules.sales_pos.dialogs.redeem_points_dialog import RedeemPointsDialog
from frontend.desktop.modules.sales_pos.dialogs.resume_sale_dialog import ResumeSaleDialog
from frontend.desktop.modules.sales_pos.dialogs.return_sale_dialog import ReturnSaleDialog
from frontend.desktop.modules.sales_pos.dialogs.weight_confirmation_dialog import (
    WEIGHT_SOURCE_MANUAL,
    WeightCaptureDialog,
)

logger = logging.getLogger(__name__)

#: Ruta del módulo de Caja (Corte Z vive ahí).
CASH_REGISTER_ROUTE = "cash_register.workspace"

#: Fábricas de diálogo, por nombre del símbolo de este módulo. Se resuelven al
#: construir la pantalla (no al importar) para que las pruebas puedan
#: sustituirlas sin abrir ventanas modales reales.
_DIALOG_NAMES = {
    "weight": "WeightCaptureDialog",
    "quantity": "QuantityDialog",
    "cancel": "CancelSaleDialog",
    "resume": "ResumeSaleDialog",
    "posted_sale": "PostedSalePickerDialog",
    "invoice": "InvoiceRequestDialog",
    "return": "ReturnSaleDialog",
    "payment": "PaymentDialog",
    "discount": "DiscountDialog",
    "quick_customer": "QuickCustomerDialog",
    "redeem": "RedeemPointsDialog",
    "coupon": "CouponDialog",
    "prepaid": "PrepaidVoucherDialog",
}


class SalesPosWorkspace(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("salesPosWorkspace")
        self._presenter = presenter
        self._capabilities = presenter.capabilities()
        self._sale_id: str | None = None
        self._sale = None
        self._sale_started = False
        self._last_completed_sale_id: str | None = None
        self.dialogs = {key: globals()[name] for key, name in _DIALOG_NAMES.items()}
        self._customer_display_window: CustomerDisplayWindow | None = None
        self._customer_display_gateway: QtCustomerDisplayGateway | None = None
        self._cart_is_idle = True
        self._ad_rotation: list = []
        self._ad_index = 0
        self._ad_elapsed = 0
        self._ad_timer = QTimer(self)
        self._ad_timer.setInterval(1000)
        self._ad_timer.timeout.connect(self._on_ad_timer_tick)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.cashier_bar = CashierBar(presenter, self)
        self.cashier_bar.customer_display_toggled.connect(self._on_customer_display_toggled)
        self.cashier_bar.z_cut_requested.connect(self._on_z_cut_requested)
        root.addWidget(self.cashier_bar)

        self._splitter = QSplitter(self)
        self.catalog = CatalogPanel(presenter, self)
        self.catalog.product_selected.connect(self._on_product_selected)
        self.catalog.code_scanned.connect(self._on_code_scanned)
        self._splitter.addWidget(self.catalog)

        self.checkout = CheckoutPanel(presenter, self)
        self.checkout.customer_selected.connect(self._on_customer_selected)
        self.checkout.customer_clear_requested.connect(self._on_customer_cleared)
        self.checkout.line_quantity_requested.connect(self._on_line_quantity_requested)
        self.checkout.line_remove_requested.connect(self._on_line_remove_requested)
        self.checkout.checkout_requested.connect(self._on_checkout_requested)
        self.checkout.suspend_requested.connect(self._on_suspend_requested)
        self.checkout.resume_requested.connect(self._on_resume_requested)
        self.checkout.cancel_requested.connect(self._on_cancel_requested)
        self.checkout.return_requested.connect(self._on_return_requested)
        self.checkout.reprint_requested.connect(self._on_reprint_requested)
        self.checkout.invoice_requested.connect(self._on_invoice_requested)
        self.checkout.discount_requested.connect(self.open_discount_dialog)
        self.checkout.quick_discount_requested.connect(self._on_quick_discount)
        self._splitter.addWidget(self.checkout)

        self.checkout.customer.quick_create_button().clicked.connect(
            self._on_quick_create_customer)
        self.checkout.customer.redeem_requested.connect(self._on_redeem_requested)
        self.checkout.customer.coupon_requested.connect(self._on_coupon_requested)
        self.checkout.customer.prepaid_requested.connect(self._on_prepaid_requested)

        # El catálogo absorbe el ancho extra; el panel de venta conserva su ancho
        # acotado (380-600 px, en `CheckoutPanel`).
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 0)
        self._splitter.setChildrenCollapsible(False)

        root.addWidget(self._splitter, stretch=1)

        self._wire_shortcuts()
        self.catalog.load_categories()

    def showEvent(self, event) -> None:
        """La pantalla se construye antes del login; la venta se abre la
        primera vez que se MUESTRA con un usuario autenticado."""
        super().showEvent(event)
        if not self._sale_started and self._presenter.current_user_id():
            self._sale_started = True
            self.cashier_bar.refresh_identity()
            self.cashier_bar.refresh_shift_status()
            self.cashier_bar.refresh_device_health()
            self._start_new_sale()

    def _wire_shortcuts(self) -> None:
        """Atajos reales (§54): cada tecla dispara el mismo manejador que su
        botón — nunca una segunda ruta divergente."""
        bindings = {
            "F2": self.catalog.focus_search,
            "F5": self.open_discount_dialog,
            "F6": self._on_suspend_requested,
            "F7": self._on_resume_requested,
            "F8": self._on_cancel_requested,
            "F9": self._on_checkout_requested,
            "F10": self._on_return_requested,
            "F11": self._on_invoice_requested,
            "F12": self._on_reprint_requested,
        }
        self._shortcuts = [
            QShortcut(QKeySequence(key), self, activated=handler)
            for key, handler in bindings.items()
        ]

    # ── venta en curso ───────────────────────────────────────────────────
    def _start_new_sale(self) -> None:
        result = self._presenter.start_sale()
        self._sale_id = result.entity_id if result.success else None
        # Sin modal: esto corre al MOSTRAR la pantalla; el motivo queda donde el
        # cajero mira, en el lugar del carrito.
        self.checkout.cart.set_empty_message(
            None if result.success else f"No se pudo abrir la venta: {result.message}")
        self._refresh()

    def _refresh(self) -> None:
        sale = self._presenter.get_sale(self._sale_id) if self._sale_id else None
        self._sale = sale
        self._cart_is_idle = sale is None or not sale.lines
        customer = self._presenter.customer_summary(sale.customer_id) if sale else None
        self.checkout.render_sale(sale, customer)
        self.checkout.refresh_suspended_count()
        self.cashier_bar.refresh_suspended_count()
        self.catalog.refresh()
        if self._customer_display_gateway is not None:
            self._push_customer_display()

    def _has_lines(self) -> bool:
        return bool(self._sale is not None and self._sale.lines)

    def _warn(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)

    def _info(self, title: str, message: str) -> None:
        QMessageBox.information(self, title, message)

    # ── catálogo, escáner y peso (§15-19) ────────────────────────────────
    def _on_product_selected(self, product) -> None:
        if not self._sale_id:
            return
        result = self._presenter.add_product(sale_id=self._sale_id, product=product)
        if result.error_code == "WEIGHT_REQUIRED":
            result = self._add_weighed(product)
            if result is None:
                return
        self._after_line_change(result, "No se pudo agregar el producto")

    def _add_weighed(self, product):
        dialog = self.dialogs["weight"](
            self._presenter, product_name=product.name, unit_price=product.effective_price,
            unit=product.unit or "KG", parent=self)
        if not dialog.exec_() or dialog.weight is None:
            return None
        return self._presenter.add_product(
            sale_id=self._sale_id, product=product, quantity=dialog.weight,
            weight_source=dialog.weight_source or WEIGHT_SOURCE_MANUAL)

    def _on_code_scanned(self, code: str) -> None:
        """Un lector de código es un teclado rápido seguido de Enter (§17);
        `context="AUTO"`: producto primero, luego tarjeta de cliente."""
        if not self._sale_id:
            return
        result = self._presenter.scan_code(sale_id=self._sale_id, code=code, context="AUTO")
        self.catalog.clear_search()
        if result.error_code == "WEIGHT_REQUIRED":
            result = self._add_weighed(result.data["product"])
            if result is None:
                return
        if result.success:
            self.catalog.set_scanner_status("Escáner: leído", "success")
            self._refresh()
        else:
            self.catalog.set_scanner_status("Escáner: no reconocido", "warning")
            self._warn("Código no reconocido", result.message)

    def _after_line_change(self, result, title: str) -> None:
        if result.success:
            self._refresh()
        else:
            self._warn(title, result.message)

    # ── carrito (§12) ────────────────────────────────────────────────────
    def _line(self, line_id: str):
        if self._sale is None:
            return None
        return next((line for line in self._sale.lines if line.id == line_id), None)

    def _on_line_quantity_requested(self, line_id: str) -> None:
        line = self._line(line_id)
        if line is None:
            return
        name = str(line.product_snapshot.get("name") or line.product_id)
        if line.product_snapshot.get("by_weight") or line.weight_source:
            dialog = self.dialogs["weight"](
                self._presenter, product_name=name, unit_price=line.unit_price,
                unit=line.quantity_unit, current_weight=line.quantity, parent=self)
            accepted = dialog.exec_() and dialog.weight is not None
            quantity = dialog.weight if accepted else None
        else:
            dialog = self.dialogs["quantity"](
                product_name=name, unit=line.quantity_unit, current=line.quantity, parent=self)
            accepted = dialog.exec_() and dialog.quantity is not None
            quantity = dialog.quantity if accepted else None
        if quantity is None:
            return
        result = self._presenter.update_line_quantity(
            sale_id=self._sale_id, line_id=line_id, quantity=quantity)
        self._after_line_change(result, "No se pudo cambiar la cantidad")

    def _on_line_remove_requested(self, line_id: str) -> None:
        result = self._presenter.remove_line(sale_id=self._sale_id, line_id=line_id)
        self._after_line_change(result, "No se pudo quitar la línea")

    # ── cliente (§21-23) ─────────────────────────────────────────────────
    def _on_customer_selected(self, customer_id: str) -> None:
        if not self._sale_id:
            return
        result = self._presenter.assign_customer(sale_id=self._sale_id, customer_id=customer_id)
        self._after_line_change(result, "No se pudo asignar el cliente")

    def _on_customer_cleared(self) -> None:
        if not self._sale_id:
            return
        result = self._presenter.clear_customer(sale_id=self._sale_id)
        self._after_line_change(result, "No se pudo quitar el cliente")

    def _on_quick_create_customer(self) -> None:
        dialog = self.dialogs["quick_customer"](self._presenter, self)
        if dialog.exec_() and dialog.customer_id and self._sale_id:
            self._on_customer_selected(dialog.customer_id)

    def _on_redeem_requested(self) -> None:
        """Canje de puntos (§38): descuenta del ticket lo que Fidelidad permita."""
        if self._sale is None or not self._sale.customer_id:
            return
        if not self._has_lines():
            self._info("Canjear puntos", "Agrega productos antes de canjear puntos.")
            return
        preview = self._presenter.redemption_preview(self._sale)
        if preview is None:
            self._warn("Canjear puntos", "Fidelidad no respondió; intenta de nuevo.")
            return
        dialog = self.dialogs["redeem"](self._presenter, sale=self._sale, preview=preview,
                                        parent=self)
        if dialog.exec_():
            self._refresh()

    def _on_coupon_requested(self) -> None:
        """Cupones del ticket (2026-10-03): Fidelidad decide si aplican."""
        if self._sale is None or not self._has_lines():
            self._info("Cupón", "Agrega productos antes de aplicar un cupón.")
            return
        dialog = self.dialogs["coupon"](self._presenter, sale=self._sale, parent=self)
        dialog.exec_()
        if dialog.changed:
            self._refresh()

    def _on_prepaid_requested(self) -> None:
        """Vale prepagado como línea del ticket (2026-10-03)."""
        if self._sale is None:
            return
        dialog = self.dialogs["prepaid"](self._presenter, sale=self._sale, parent=self)
        dialog.exec_()
        if dialog.changed:
            self._refresh()

    def aplicar_contexto(self, context: dict) -> None:
        """Llega desde el perfil de cliente ("Nueva venta"): asigna el cliente
        (id de Customer Master, sin puente legacy)."""
        customer_id = str((context or {}).get("customer_id") or "").strip()
        if not customer_id or not self._sale_id:
            return
        result = self._presenter.assign_customer(sale_id=self._sale_id, customer_id=customer_id)
        if result.success:
            self._refresh()

    # ── descuentos (§25-26) ──────────────────────────────────────────────
    def _on_quick_discount(self, percent: Decimal) -> None:
        if not self._has_lines():
            self._info("Descuento", "Agrega productos antes de aplicar un descuento.")
            return
        result = self._presenter.apply_sale_discount_percent(
            sale_id=self._sale_id, discount_percent=percent)
        if result.success:
            self._refresh()
            return
        if result.error_code in ("DISCOUNT_NOT_ALLOWED", "BELOW_MINIMUM"):
            # Necesita autorización en caliente: el diálogo pide quién autoriza.
            self._warn("Descuento", f"{result.message}\n\nUsa «Personalizado» para que otro "
                       "usuario lo autorice.")
            return
        self._warn("Descuento", result.message)

    def open_discount_dialog(self) -> None:
        if not self._sale_id:
            return
        dialog = self.dialogs["discount"](self._presenter, sale_id=self._sale_id, parent=self)
        if dialog.exec_() and dialog.applied:
            self._refresh()

    # ── cobro (§30-38) ───────────────────────────────────────────────────
    def _on_checkout_requested(self) -> None:
        if not self._sale_id or not self._has_lines():
            return
        # Fase 6: sin turno de caja no se cobra; se avisa ANTES de abrir el
        # cobro (una vez registrados los pagos, la venta no vuelve al carrito).
        problema = self._presenter.open_shift_problem()
        self.cashier_bar.refresh_shift_status()
        if problema:
            self._warn("Turno de caja", problema)
            return
        dialog = self.dialogs["payment"](
            self._presenter, sale_id=self._sale_id, total_due=self._sale.total,
            has_customer=bool(self._sale.customer_id), parent=self)
        if not (dialog.exec_() and dialog.completed):
            self._refresh()
            return
        sale_id = self._sale_id
        self._last_completed_sale_id = sale_id
        self._announce_completed(sale_id, change=dialog.change)
        self._start_new_sale()

    def _announce_completed(self, sale_id: str, *, change: Decimal) -> None:
        """Folio, cambio y ticket (§46: el ticket se pide DESPUÉS de confirmar
        la venta). Un ticket no impreso no deshace nada: se dice por qué."""
        sale = self._presenter.get_sale(sale_id)
        folio = folio_of(sale) if sale is not None else sale_id[-8:]
        partes = [f"Venta {folio} completada."]
        if change > 0:
            partes.append(f"Cambio: ${change:,.2f}")
        ticket = self._presenter.print_receipt(sale_id=sale_id)
        if ticket.success:
            partes.append("Ticket enviado a la impresora.")
        else:
            partes.append(f"El ticket NO se imprimió: {ticket.message}\n"
                          "Puedes reimprimirlo con F12.")
        self._info("Venta completada", "\n\n".join(partes))

    # ── suspender / reanudar / cancelar (§40-42) ─────────────────────────
    def _on_suspend_requested(self) -> None:
        if not self._sale_id:
            return
        if not self._has_lines():
            self._info("Suspender", "No hay productos en la venta.")
            return
        result = self._presenter.suspend_sale(sale_id=self._sale_id)
        if result.success:
            self._start_new_sale()
        else:
            self._warn("No se pudo suspender", result.message)

    def _on_resume_requested(self) -> None:
        suspended = self._presenter.list_suspended()
        if not suspended:
            self._info("Sin ventas suspendidas", "No hay ventas suspendidas.")
            return
        dialog = self.dialogs["resume"](suspended, parent=self)
        if not dialog.exec_() or not dialog.sale_id:
            return
        if self._has_lines():
            # La venta en curso no se pierde: se suspende antes de cambiar.
            parked = self._presenter.suspend_sale(sale_id=self._sale_id)
            if not parked.success:
                self._warn("No se pudo suspender la venta en curso", parked.message)
                return
        result = self._presenter.resume_sale(sale_id=dialog.sale_id)
        if result.success:
            self._sale_id = dialog.sale_id
            self._refresh()
        else:
            self._warn("No se pudo reanudar", result.message)

    def _on_cancel_requested(self) -> None:
        if not self._sale_id or not self._has_lines():
            return
        dialog = self.dialogs["cancel"](
            line_count=len(self._sale.lines), total_text=f"${self._sale.total:,.2f}", parent=self)
        if not dialog.exec_() or not dialog.reason:
            return
        result = self._presenter.cancel_sale(sale_id=self._sale_id, reason=dialog.reason)
        if result.success:
            self._start_new_sale()
        else:
            self._warn("No se pudo cancelar", result.message)

    # ── postventa (§43-48) ───────────────────────────────────────────────
    def _on_return_requested(self) -> None:
        if not self._capabilities.sale_return:
            return
        dialog = self.dialogs["return"](
            self._presenter, can_reverse=self._capabilities.sale_reverse, parent=self)
        if self._last_completed_sale_id:
            dialog.select_sale(self._last_completed_sale_id)
        dialog.exec_()
        if dialog.changed:
            self._refresh()

    def _pick_posted_sale(self, *, title: str, ok_text: str, ask_reason: bool = False,
                          default_reason: str = ""):
        dialog = self.dialogs["posted_sale"](
            self._presenter, title=title, ok_text=ok_text, ask_reason=ask_reason,
            default_reason=default_reason, parent=self)
        if self._last_completed_sale_id:
            dialog.focus_sale(self._last_completed_sale_id)
        if not dialog.exec_() or dialog.sale is None:
            return None, None
        return dialog.sale, dialog.reason

    def _on_reprint_requested(self) -> None:
        if not self._capabilities.receipt_reprint:
            return
        sale, reason = self._pick_posted_sale(
            title="Reimprimir ticket", ok_text="Reimprimir", ask_reason=True,
            default_reason="El cliente pidió otra copia")
        if sale is None:
            return
        result = self._presenter.reprint_receipt(sale_id=sale.id, reason=reason)
        if result.success:
            self._info("Reimpresión", f"Ticket {folio_of(sale)} enviado a la impresora.")
        else:
            self._warn("No se pudo reimprimir", result.message)

    def _on_invoice_requested(self) -> None:
        if not self._capabilities.invoice_request:
            return
        sale, _reason = self._pick_posted_sale(title="Solicitar factura", ok_text="Continuar")
        if sale is None:
            return
        dialog = self.dialogs["invoice"](
            folio=folio_of(sale), total_text=f"${sale.total:,.2f}", parent=self)
        if not dialog.exec_():
            return
        result = self._presenter.request_invoice(
            sale_id=sale.id, tax_identifier=dialog.tax_identifier,
            legal_name=dialog.legal_name, cfdi_use=dialog.cfdi_use)
        if result.success:
            self._info("Factura solicitada",
                       f"Factura de la venta {folio_of(sale)} solicitada. Fiscal la timbra.")
        else:
            self._warn("No se pudo solicitar la factura", result.message)

    def _on_z_cut_requested(self) -> None:
        """El Corte Z es de Caja: se navega a su módulo (el shell canónico
        expone `navigate`)."""
        window = self.window()
        navigate = getattr(window, "navigate", None)
        if callable(navigate):
            navigate(CASH_REGISTER_ROUTE)
        else:
            self._info("Corte Z", "Abre el módulo Caja para hacer el corte de tu turno.")

    # ── refresco en caliente (catálogo/sucursales) ───────────────────────
    def refresh_products(self) -> None:
        self.catalog.refresh()

    def refresh_branches(self) -> None:
        self.catalog.refresh()

    # ── pantalla del cliente (SET-17) ────────────────────────────────────
    def _on_customer_display_toggled(self, checked: bool) -> None:
        if checked:
            self._customer_display_window = CustomerDisplayWindow(self)
            self._customer_display_gateway = QtCustomerDisplayGateway(self._customer_display_window)
            self._push_customer_display()
            self._ad_rotation = []
            self._ad_index = 0
            self._ad_elapsed = 0
            self._ad_timer.start()
        else:
            self._ad_timer.stop()
            if self._customer_display_window is not None:
                self._customer_display_window.close()
            self._customer_display_window = None
            self._customer_display_gateway = None

    def _push_customer_display(self) -> None:
        """Mejor esfuerzo: una falla de la pantalla del cliente nunca detiene
        al cajero."""
        try:
            self._presenter.push_customer_display(
                gateway=self._customer_display_gateway, sale_id=self._sale_id)
        except Exception:
            logger.exception("No se pudo actualizar la pantalla del cliente")

    def _on_ad_timer_tick(self) -> None:
        """Rotación de publicidad en reposo, un segundo a la vez. Nunca corre
        con el carrito lleno."""
        if not self._cart_is_idle or self._customer_display_window is None:
            return
        try:
            if not self._ad_rotation:
                self._ad_rotation = list(self._presenter.resolve_idle_ads())
                self._ad_index = 0
                self._ad_elapsed = 0
                if self._ad_rotation:
                    self._show_current_ad()
                return

            self._ad_elapsed += 1
            current = self._ad_rotation[self._ad_index]
            if self._ad_elapsed >= current.duration_seconds:
                self._presenter.record_ad_impression(
                    placement_id=current.placement_id, duration_shown_seconds=current.duration_seconds)
                self._ad_index += 1
                self._ad_elapsed = 0
                if self._ad_index >= len(self._ad_rotation):
                    self._ad_rotation = list(self._presenter.resolve_idle_ads())
                    self._ad_index = 0
                if self._ad_rotation:
                    self._show_current_ad()
        except Exception:
            logger.exception("No se pudo actualizar la rotación de publicidad")

    def _show_current_ad(self) -> None:
        ad = self._ad_rotation[self._ad_index]
        self._customer_display_window.render_idle_ad(ad.content_type, ad.title, ad.body)
