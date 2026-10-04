"""Presenter bridge between the Sales/POS desktop UI and the real backend
built across SALES-2..18 (POS-19).

Mirrors `frontend/desktop/modules/customers_crm/customers_crm_presenter.py::
CustomerCrmPresenter`'s shape exactly: components ask this presenter for
capabilities and named business outcomes, never touching a repository, a
use case class, or a raw connection themselves (enforced the same way CRM's
own UI guardrails do — see `tests/architecture/test_sales_pos_ui_guardrails.py`).
`query_services`/`command_handlers` are injected dicts, looked up by key,
never imported/constructed here — wiring them to a live connection is
`composition.py`'s job alone. Every write method degrades to
`SaleResult.fail(..., "NOT_WIRED")` when its handler isn't wired, matching
the same "a component must always have something safe to render/react to"
contract CRM's presenter established.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from decimal import Decimal

from backend.application.sales.result import SaleResult
from frontend.desktop.modules.sales_pos.capability_resolver import resolve_sales_pos_capabilities
from frontend.desktop.modules.sales_pos.view_models import CustomerSummary, SalesPosCapabilities

_NOT_WIRED = "Esta acción no está disponible: falta la conexión al backend."
logger = logging.getLogger("spj.sales_pos.presenter")


class SalesPosPresenter:
    def __init__(
        self, *, session_context,
        query_services: dict[str, object] | None = None,
        command_handlers: dict[str, Callable[..., object]] | None = None,
    ) -> None:
        self._session = session_context
        self._query_services = dict(query_services or {})
        self._command_handlers = dict(command_handlers or {})

    # ── session / capabilities ──────────────────────────────────────────

    def can(self, permission: str) -> bool:
        checker = getattr(self._session, "tiene_permiso", None)
        return bool(callable(checker) and checker(permission))

    def capabilities(self) -> SalesPosCapabilities:
        return resolve_sales_pos_capabilities(self.can)

    def current_user_id(self) -> str:
        return str(getattr(self._session, "user_id", "") or "")

    def current_branch_id(self) -> str:
        return str(getattr(self._session, "active_branch_id", "") or "")

    def cashier_name(self) -> str:
        """Para la barra superior (§1: "Cajero")."""
        for attr in ("nombre_completo", "usuario", "user_name"):
            value = str(getattr(self._session, attr, "") or "").strip()
            if value:
                return value
        return ""

    def branch_name(self) -> str:
        for attr in ("sucursal_nombre", "branch_name"):
            value = str(getattr(self._session, attr, "") or "").strip()
            if value:
                return value
        return ""

    def query_service(self, key: str) -> object | None:
        return self._query_services.get(key)

    def command_handler(self, key: str) -> Callable[..., object] | None:
        return self._command_handlers.get(key)

    def _run(self, key: str, **kwargs) -> SaleResult:
        handler = self.command_handler(key)
        if handler is None:
            return SaleResult.fail(_NOT_WIRED, "NOT_WIRED")
        return handler(**kwargs)

    # ── catalog (SALES-7) ────────────────────────────────────────────────

    def catalog_search(self, *, search: str = "", category_id: str | None = None) -> tuple:
        service = self.query_service("catalog")
        if service is None:
            return ()
        return service.search(
            branch_id=self.current_branch_id(), search=search, category_id=category_id)

    def categories(self) -> tuple:
        service = self.query_service("catalog")
        if service is None:
            return ()
        return service.category_options()

    # ── cart (SALES-6/8/13) ──────────────────────────────────────────────

    def get_sale(self, sale_id: str):
        service = self.query_service("sale_query")
        if service is None:
            return None
        return service.get(sale_id, requester_user_id=self.current_user_id())

    def start_sale(self, *, workstation_id: str | None = None) -> SaleResult:
        return self._run(
            "start_sale", branch_id=self.current_branch_id(),
            cashier_user_id=self.current_user_id(), operation_id=_new_op(),
            actor_user_id=self.current_user_id(), workstation_id=workstation_id)

    def add_line(self, *, sale_id: str, product_id: str, quantity: Decimal,
                 unit_price: Decimal, product_snapshot: dict | None = None,
                 weight_source: str | None = None, quantity_unit: str = "PZA") -> SaleResult:
        resolved = self._resolve_effective_price(
            sale_id=sale_id, product_id=product_id, quantity=quantity)
        return self._run(
            "add_line", sale_id=sale_id, product_id=product_id, quantity=quantity,
            unit_price=unit_price if resolved is None else resolved,
            actor_user_id=self.current_user_id(),
            operation_id=_new_op(), product_snapshot=product_snapshot,
            weight_source=weight_source, quantity_unit=quantity_unit or "PZA")

    def add_product(self, *, sale_id: str, product, quantity: Decimal | None = None,
                    weight_source: str | None = None) -> SaleResult:
        """Agrega un renglón del catálogo con SU unidad. Para un producto por
        peso `quantity` es el peso capturado (validado por el dominio)."""
        if not product.sellable:
            return SaleResult.fail(
                f"{product.name}: " + ("; ".join(product.warnings) or "no se puede vender"),
                "PRODUCT_NOT_SELLABLE")
        if product.sold_by_weight and quantity is None:
            return SaleResult.fail(f"{product.name} se vende por peso: captura el peso.",
                                   "WEIGHT_REQUIRED", product=product)
        return self.add_line(
            sale_id=sale_id, product_id=product.product_id,
            quantity=quantity if quantity is not None else Decimal("1"),
            unit_price=product.effective_price, quantity_unit=product.unit or "PZA",
            weight_source=weight_source,
            product_snapshot={"name": product.name, "sku": product.sku, "unit": product.unit,
                              "by_weight": bool(product.sold_by_weight)})

    def validate_weight(self, weight) -> tuple[Decimal | None, str]:
        """(peso, "") si el dominio lo acepta; si no, (None, motivo)."""
        check = self.query_service("weight_policy")
        if check is None:
            return None, "La captura de peso no está disponible."
        return check(weight)


    def _resolve_effective_price(self, *, sale_id: str, product_id: str,
                                 quantity: Decimal) -> Decimal | None:
        """§20 (master prompt): the price actually charged must come from the
        canonical Pricing engine (branch/customer/volume-aware), not from
        whatever static BASE-list price the catalog grid showed for
        browsing (`SalesCatalogQueryService.search()` stays on that flat
        price deliberately — one bulk query for the whole grid, see its own
        docstring). Resolving per-line here is cheap (one product) and is
        exactly the moment `SalesPricingClient`'s own docstring names as its
        intended call site. Returns None — caller's own price wins — when
        pricing isn't wired, nothing is configured for this product, or the
        lookup fails; never blocks a sale over a pricing lookup problem."""
        service = self.query_service("pricing")
        if service is None:
            return None
        sale = self.get_sale(sale_id)
        customer_id = sale.customer_id if sale is not None else None
        try:
            return service.effective_price(
                product_id, branch_id=self.current_branch_id(),
                customer_id=customer_id, quantity=quantity)
        except Exception:
            logger.exception(
                "No se pudo resolver el precio canónico de %s; se usa el precio "
                "de catálogo.", product_id)
            return None

    def update_line_quantity(self, *, sale_id: str, line_id: str, quantity: Decimal) -> SaleResult:
        return self._run(
            "update_line_quantity", sale_id=sale_id, line_id=line_id, quantity=quantity,
            actor_user_id=self.current_user_id(), operation_id=_new_op())

    def remove_line(self, *, sale_id: str, line_id: str) -> SaleResult:
        return self._run(
            "remove_line", sale_id=sale_id, line_id=line_id,
            actor_user_id=self.current_user_id(), operation_id=_new_op())

    def scan_code(self, *, sale_id: str, code: str, context: str) -> SaleResult:
        return self._run(
            "scan_code", sale_id=sale_id, code=code, context=context,
            branch_id=self.current_branch_id(), actor_user_id=self.current_user_id(),
            operation_id=_new_op())

    # ── customer (SALES-10) ──────────────────────────────────────────────

    def search_customers(self, query: str) -> list:
        service = self.query_service("customer_search")
        if service is None:
            return []
        return service.lookup(query, actor_user_id=self.current_user_id())

    def customer_summary(self, customer_id: str | None) -> CustomerSummary | None:
        """Nombre y teléfono (Clientes) + puntos y nivel (Fidelidad) del
        cliente asignado. Si Fidelidad no responde, se muestra el cliente sin
        puntos — nunca "0 puntos" inventados."""
        if not customer_id:
            return None
        service = self.query_service("customer_search")
        found = None
        if service is not None and hasattr(service, "get"):
            found = service.get(customer_id, actor_user_id=self.current_user_id())
        points = tier = None
        loyalty = self.query_service("loyalty_summary")
        if loyalty is not None:
            try:
                summary = loyalty.peek_loyalty_summary(customer_id=customer_id)
                points, tier = int(summary.points_balance), (summary.tier or None)
            except Exception:
                logger.exception("Resumen de fidelidad no disponible para %s", customer_id)
        return CustomerSummary(
            customer_id=customer_id,
            name=found.display_name if found else "Cliente asignado",
            phone=found.phone_e164 if found else None, points=points, tier=tier)

    def clear_customer(self, *, sale_id: str) -> SaleResult:
        """De vuelta a venta de mostrador (`AssignCustomerToSaleUseCase` con None)."""
        return self._run(
            "assign_customer", sale_id=sale_id, customer_id=None,
            actor_user_id=self.current_user_id(), operation_id=_new_op())

    def assign_customer(self, *, sale_id: str, customer_id: str) -> SaleResult:
        return self._run(
            "assign_customer", sale_id=sale_id, customer_id=customer_id,
            actor_user_id=self.current_user_id(), operation_id=_new_op())

    def quick_create_customer(self, *, display_name: str, phone_e164: str | None = None) -> SaleResult:
        return self._run(
            "quick_create_customer", actor_user_id=self.current_user_id(),
            operation_id=_new_op(), display_name=display_name, phone_e164=phone_e164)

    def scan_loyalty_card(self, *, sale_id: str, card_code: str) -> SaleResult:
        return self._run(
            "scan_loyalty_card", sale_id=sale_id, card_code=card_code,
            actor_user_id=self.current_user_id(), operation_id=_new_op())

    def points_to_earn(self, sale) -> str | None:
        """Texto de "Puntos a ganar" (§29) con las reglas de Fidelidad. None si
        Fidelidad no responde: la tarjeta lo dice en vez de inventar."""
        estimate = self.query_service("points_to_earn")
        if estimate is None or sale is None:
            return None
        if not sale.customer_id:
            return "Asigna un cliente"
        try:
            puntos = int(estimate(sale=sale))
        except Exception:
            logger.exception("Estimación de puntos no disponible")
            return None
        return f"{puntos} pts"

    def redemption_preview(self, sale) -> dict | None:
        """Qué puede canjear el cliente de la venta (mínimo, tope y saldo los
        aplica Fidelidad). None si no hay cliente o Fidelidad no responde."""
        loyalty = self.query_service("loyalty_summary")
        if loyalty is None or sale is None or not sale.customer_id:
            return None
        try:
            return loyalty.preview_redemption(
                customer_id=sale.customer_id, subtotal=sale.gross_subtotal)
        except Exception:
            logger.exception("Vista previa de canje no disponible")
            return None

    def redeem_loyalty_points(self, *, sale_id: str, points: int) -> SaleResult:
        return self._run(
            "redeem_loyalty_points", sale_id=sale_id, points=points,
            actor_user_id=self.current_user_id(), operation_id=_new_op())

    # ── discounts (SALES-8) ──────────────────────────────────────────────

    def verify_authorizer(self, username: str, password: str) -> tuple[str | None, str]:
        """(user_id, "") si usuario y clave son de un usuario activo; si no,
        (None, motivo). El permiso para autorizar lo revalida el caso de uso."""
        verifier = self.query_service("authorizer_credentials")
        if verifier is None:
            return None, "La verificación del autorizador no está disponible."
        from backend.security.authentication.errors import AuthenticationFailedError
        from backend.security.sessions.errors import AccountLockedError
        try:
            return verifier(username=username, password=password), ""
        except (AuthenticationFailedError, AccountLockedError) as exc:
            return None, str(exc)

    def apply_sale_discount(self, *, sale_id: str, discount_amount: Decimal,
                            authorizer_user_id: str | None = None,
                            reason: str | None = None) -> SaleResult:
        return self._run(
            "apply_sale_discount", sale_id=sale_id, discount_amount=discount_amount,
            actor_user_id=self.current_user_id(), operation_id=_new_op(),
            authorizer_user_id=authorizer_user_id, reason=reason)

    def apply_sale_discount_percent(self, *, sale_id: str, discount_percent: Decimal,
                                    authorizer_user_id: str | None = None,
                                    reason: str | None = None) -> SaleResult:
        return self._run(
            "apply_sale_discount_percent", sale_id=sale_id, discount_percent=discount_percent,
            actor_user_id=self.current_user_id(), operation_id=_new_op(),
            authorizer_user_id=authorizer_user_id, reason=reason)

    def apply_line_discount(self, *, sale_id: str, line_id: str, discount_amount: Decimal,
                            authorizer_user_id: str | None = None,
                            reason: str | None = None) -> SaleResult:
        return self._run(
            "apply_line_discount", sale_id=sale_id, line_id=line_id,
            discount_amount=discount_amount, actor_user_id=self.current_user_id(),
            operation_id=_new_op(), authorizer_user_id=authorizer_user_id, reason=reason)

    # ── payment / checkout (SALES-13/14) ─────────────────────────────────

    def record_payment(self, *, sale_id: str, method: str, amount: Decimal,
                       reference: str | None = None) -> SaleResult:
        return self._run(
            "record_payment", sale_id=sale_id, method=method, amount=amount,
            actor_user_id=self.current_user_id(), operation_id=_new_op(), reference=reference)

    def begin_checkout(self, *, sale_id: str) -> SaleResult:
        return self._run(
            "begin_checkout", sale_id=sale_id, actor_user_id=self.current_user_id(),
            operation_id=_new_op())

    def checkout_sale(self, *, sale_id: str, authorizer_user_id: str | None = None,
                      reason: str | None = None) -> SaleResult:
        """`authorizer_user_id`/`reason`: la autorización en caliente para
        cobrar sin existencia (Fase 6); sólo se piden si el cobro la exige."""
        return self._run(
            "checkout_sale", sale_id=sale_id, actor_user_id=self.current_user_id(),
            operation_id=_new_op(), authorizer_user_id=authorizer_user_id, reason=reason)

    def cash_tender(self, *, total: Decimal, received: Decimal):
        """Cambio y faltante del efectivo, decididos por `CashPaymentPolicy`."""
        evaluate = self.query_service("cash_tender")
        if evaluate is None:
            return None
        return evaluate(total=total, received=received)

    def payment_amount_problem(self, *, method: str, amount: Decimal,
                               outstanding: Decimal) -> str | None:
        """Por qué el dominio rechazaría este pago (sólo el efectivo admite
        cambio), ANTES de iniciar el cobro — después ya no hay vuelta al carrito."""
        check = self.query_service("payment_amount_check")
        if check is None:
            return None
        return check(method=method, amount=amount, outstanding=outstanding)

    def payment_methods(self, *, has_customer: bool) -> tuple[str, ...]:
        """Los métodos que este usuario puede cobrar (§31, §61). Crédito sólo
        con cliente asignado (§36: "No mostrar Crédito cuando el cliente no
        cumple"); si su línea alcanza lo decide el caso de uso al registrar."""
        caps = self.capabilities()
        methods = []
        for code, allowed in (("CASH", caps.payment_cash), ("CARD", caps.payment_card),
                              ("TRANSFER", caps.payment_transfer),
                              ("CREDIT", caps.payment_credit and has_customer),
                              ("MERCADO_PAGO", caps.payment_mercado_pago)):
            if allowed:
                methods.append(code)
        return tuple(methods)

    def open_shift_problem(self) -> str | None:
        """Por qué no se puede cobrar por falta de turno, o None. Se pregunta
        ANTES de abrir el cobro: una vez registrados los pagos la venta ya no
        vuelve al carrito."""
        check = self.query_service("cash_shift")
        if check is None:
            return None
        return check(branch_id=self.current_branch_id(), cashier_user_id=self.current_user_id())

    # ── suspend / resume / cancel (SALES-9/15) ───────────────────────────

    def suspend_sale(self, *, sale_id: str, max_suspended_sales: int = 5) -> SaleResult:
        return self._run(
            "suspend_sale", sale_id=sale_id, actor_user_id=self.current_user_id(),
            operation_id=_new_op(), max_suspended_sales=max_suspended_sales)

    def resume_sale(self, *, sale_id: str) -> SaleResult:
        return self._run(
            "resume_sale", sale_id=sale_id, actor_user_id=self.current_user_id(),
            operation_id=_new_op())

    def cancel_sale(self, *, sale_id: str, reason: str) -> SaleResult:
        return self._run(
            "cancel_sale", sale_id=sale_id, reason=reason,
            actor_user_id=self.current_user_id(), operation_id=_new_op())

    def count_suspended(self) -> int:
        service = self.query_service("sale_query")
        if service is None:
            return 0
        return service.count_suspended(
            branch_id=self.current_branch_id(), requester_user_id=self.current_user_id())

    def list_suspended(self) -> tuple:
        service = self.query_service("sale_query")
        if service is None:
            return ()
        return service.list_suspended(
            branch_id=self.current_branch_id(), requester_user_id=self.current_user_id())

    # ── returns / reversal (SALES-16) ────────────────────────────────────

    def return_line(self, *, sale_id: str, line_id: str, quantity: Decimal, reason: str,
                    authorizer_user_id: str) -> SaleResult:
        return self._run(
            "return_line", sale_id=sale_id, line_id=line_id, quantity=quantity, reason=reason,
            actor_user_id=self.current_user_id(), authorizer_user_id=authorizer_user_id,
            operation_id=_new_op())

    def reverse_sale(self, *, sale_id: str, reason: str, authorizer_user_id: str) -> SaleResult:
        return self._run(
            "reverse_sale", sale_id=sale_id, reason=reason,
            actor_user_id=self.current_user_id(), authorizer_user_id=authorizer_user_id,
            operation_id=_new_op())

    # ── receipts / fiscal (SALES-17/18) ──────────────────────────────────

    def print_receipt(self, *, sale_id: str) -> SaleResult:
        """El ticket ORIGINAL, después de confirmar el cobro."""
        return self._run(
            "print_receipt", sale_id=sale_id, cajero_nombre=self.cashier_name(),
            actor_user_id=self.current_user_id(), operation_id=_new_op())

    def reprint_receipt(self, *, sale_id: str, cajero_nombre: str | None = None,
                        reason: str = "Reimpresión de ticket") -> SaleResult:
        return self._run(
            "reprint_receipt", sale_id=sale_id, cajero_nombre=cajero_nombre or self.cashier_name(),
            actor_user_id=self.current_user_id(), operation_id=_new_op(), reason=reason)

    def recent_posted_sales(self, *, limit: int = 30) -> tuple:
        """Ventas ya cobradas de la sucursal (reimprimir, facturar, devolver)."""
        service = self.query_service("sale_query")
        if service is None:
            return ()
        return service.list_recent_posted(
            branch_id=self.current_branch_id(), requester_user_id=self.current_user_id(),
            limit=limit)

    def find_posted_sale(self, folio: str):
        service = self.query_service("sale_query")
        if service is None or not (folio or "").strip():
            return None
        return service.find_posted_by_number(
            branch_id=self.current_branch_id(), sale_number=folio.strip(),
            requester_user_id=self.current_user_id())

    def request_invoice(self, *, sale_id: str, tax_identifier: str | None = None,
                        legal_name: str | None = None, cfdi_use: str | None = None) -> SaleResult:
        return self._run(
            "request_invoice", sale_id=sale_id, tax_identifier=tax_identifier,
            legal_name=legal_name, cfdi_use=cfdi_use, actor_user_id=self.current_user_id(),
            operation_id=_new_op())

    # ── hardware (SALES-12) ──────────────────────────────────────────────

    def device_health(self) -> tuple:
        """Estado de dispositivos de la sucursal. Sin el permiso de diagnóstico
        (`POS.dispositivo.diagnostico_ver`, que el cajero no trae) la barra
        muestra "N/D" en vez de reventar."""
        service = self.query_service("device_health")
        if service is None:
            return ()
        from backend.domain.sales.exceptions import SalesPermissionDeniedError
        try:
            return service.check_all(requester_user_id=self.current_user_id(),
                                     branch_id=self.current_branch_id() or None)
        except SalesPermissionDeniedError:
            return ()

    # ── customer display (SET-17) ────────────────────────────────────────

    def customer_display_state(self, sale_id: str):
        service = self.query_service("customer_display")
        if service is None:
            return None
        return service.current_state(sale_id, requester_user_id=self.current_user_id())

    def push_customer_display(self, *, gateway, sale_id: str | None) -> None:
        state = self.customer_display_state(sale_id) if sale_id else None
        handler = self.command_handler("push_customer_display")
        if handler is None:
            return
        handler(gateway=gateway, state=state, branch_id=self.current_branch_id())

    def resolve_idle_ads(self, mode: str = "IDLE") -> tuple:
        service = self.query_service("advertising")
        if service is None:
            return ()
        return service.resolve_active_ads(mode)

    def record_ad_impression(self, *, placement_id: str, duration_shown_seconds: int) -> None:
        handler = self.command_handler("record_ad_impression")
        if handler is None:
            return
        handler(placement_id=placement_id, duration_shown_seconds=duration_shown_seconds)


def _new_op() -> str:
    from backend.shared.ids import new_uuid

    return new_uuid()
