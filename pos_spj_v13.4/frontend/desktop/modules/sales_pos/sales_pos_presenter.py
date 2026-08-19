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

from collections.abc import Callable
from decimal import Decimal

from backend.application.sales.result import SaleResult
from frontend.desktop.modules.sales_pos.capability_resolver import resolve_sales_pos_capabilities
from frontend.desktop.modules.sales_pos.view_models import SalesPosCapabilities

_NOT_WIRED = "Esta acción no está disponible: falta la conexión al backend."


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
        return service.get_categories()

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
                 weight_source: str | None = None) -> SaleResult:
        return self._run(
            "add_line", sale_id=sale_id, product_id=product_id, quantity=quantity,
            unit_price=unit_price, actor_user_id=self.current_user_id(),
            operation_id=_new_op(), product_snapshot=product_snapshot,
            weight_source=weight_source)

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
        return service.search(query, actor_user_id=self.current_user_id())

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

    def redeem_loyalty_points(self, *, sale_id: str, points: int) -> SaleResult:
        return self._run(
            "redeem_loyalty_points", sale_id=sale_id, points=points,
            actor_user_id=self.current_user_id(), operation_id=_new_op())

    # ── discounts (SALES-8) ──────────────────────────────────────────────

    def apply_sale_discount(self, *, sale_id: str, discount_amount: Decimal,
                            authorizer_user_id: str | None = None,
                            reason: str | None = None) -> SaleResult:
        return self._run(
            "apply_sale_discount", sale_id=sale_id, discount_amount=discount_amount,
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

    def checkout_sale(self, *, sale_id: str) -> SaleResult:
        return self._run(
            "checkout_sale", sale_id=sale_id, actor_user_id=self.current_user_id(),
            operation_id=_new_op())

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

    def reprint_receipt(self, *, sale_id: str, cajero_nombre: str) -> SaleResult:
        return self._run(
            "reprint_receipt", sale_id=sale_id, cajero_nombre=cajero_nombre,
            actor_user_id=self.current_user_id(), operation_id=_new_op())

    def request_invoice(self, *, sale_id: str, tax_identifier: str | None = None,
                        legal_name: str | None = None, cfdi_use: str | None = None) -> SaleResult:
        return self._run(
            "request_invoice", sale_id=sale_id, tax_identifier=tax_identifier,
            legal_name=legal_name, cfdi_use=cfdi_use, actor_user_id=self.current_user_id(),
            operation_id=_new_op())

    # ── hardware (SALES-12) ──────────────────────────────────────────────

    def device_health(self) -> tuple:
        service = self.query_service("device_health")
        if service is None:
            return ()
        return service.check_all(requester_user_id=self.current_user_id())


def _new_op() -> str:
    from backend.shared.ids import new_uuid

    return new_uuid()
