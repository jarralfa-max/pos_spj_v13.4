"""Composition root for the Sales/POS desktop module (POS-19).

This is the ONLY place that wires a real, live `connection`/`session_context`
into the real backend/application/sales use cases and query services built
across SALES-2..18, and hands the result to `SalesPosPresenter`. Mirrors
`frontend/desktop/modules/customers_crm/composition.py`'s own guardrail:
takes only plain arguments — a bare `connection`, a `session_context`, and
(Sales-specific) an optional `printer_service` — never the app's whole
dependency container. The outer unwrapping step lives OUTSIDE this package,
in `modulos/ventas_pos.py`, exactly like `modulos/clientes_crm.py` does for
Customer Master/CRM.

Every use case here is real — nothing in this file fabricates behavior any
SALES-N phase didn't already build and test. Parallel, NOT wired into the
live app (`modulos/ventas.py` remains the operative POS screen) — see this
package's own `docs/refactor/SALES-19_ui_decomposition.md` for why.
"""

from __future__ import annotations

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.session_authorization import CustomerSessionPermissionChecker
from backend.application.sales.authorization import SalesAuthorizationPolicy
from backend.application.sales.queries.benefit_evaluation_service import SaleBenefitEvaluationService
from backend.application.sales.queries.catalog_query_service import SalesCatalogQueryService
from backend.application.sales.queries.device_health_query_service import DeviceHealthQueryService
from backend.application.sales.queries.sale_query_service import SaleQueryService
from backend.application.sales.session_authorization import SalesSessionPermissionChecker
from backend.application.sales.use_cases.cart_use_cases import (
    AddSaleLineUseCase,
    AssignCustomerToSaleUseCase,
    RemoveSaleLineUseCase,
    StartSaleUseCase,
    UpdateSaleLineQuantityUseCase,
)
from backend.application.sales.use_cases.checkout_use_cases import CheckoutSaleUseCase
from backend.application.sales.use_cases.customer_use_cases import (
    QuickCreateCustomerForSaleUseCase,
    ScanLoyaltyCardForSaleUseCase,
)
from backend.application.sales.use_cases.discount_use_cases import (
    ApplyLineDiscountUseCase,
    ApplySaleDiscountUseCase,
)
from backend.application.sales.use_cases.invoice_use_cases import RequestInvoiceUseCase
from backend.application.sales.use_cases.lifecycle_use_cases import (
    BeginSaleCheckoutUseCase,
    CancelSaleUseCase,
    ResumeSaleUseCase,
    SuspendSaleUseCase,
)
from backend.application.sales.use_cases.loyalty_use_cases import RedeemLoyaltyPointsUseCase
from backend.application.sales.use_cases.payment_use_cases import RecordSalePaymentUseCase
from backend.application.sales.use_cases.receipt_use_cases import ReprintReceiptUseCase
from backend.application.sales.use_cases.return_use_cases import ReturnSaleLineUseCase, ReverseSaleUseCase
from backend.application.sales.use_cases.scan_use_cases import ScanCodeRouter
from backend.domain.sales.enums import ScanContext
from frontend.desktop.modules.sales_pos.sales_pos_presenter import SalesPosPresenter


def build_sales_pos_presenter(
    connection, session_context=None, printer_service=None,
) -> SalesPosPresenter:
    checker = SalesSessionPermissionChecker(session_context)
    auth = SalesAuthorizationPolicy(checker)
    customer_auth = CustomerAuthorizationPolicy(CustomerSessionPermissionChecker(session_context))

    query_services = {
        "catalog": SalesCatalogQueryService(connection),
        "sale_query": SaleQueryService(connection, auth),
        "benefit_evaluation": SaleBenefitEvaluationService(connection, auth),
        "device_health": DeviceHealthQueryService(connection, auth),
    }

    def _h(execute, **extra):
        def handler(**kwargs):
            return execute(connection, **{**kwargs, **extra})
        return handler

    command_handlers = {
        "start_sale": _h(StartSaleUseCase(auth).execute),
        "add_line": _h(AddSaleLineUseCase(auth).execute),
        "update_line_quantity": _h(UpdateSaleLineQuantityUseCase(auth).execute),
        "remove_line": _h(RemoveSaleLineUseCase(auth).execute),
        "assign_customer": _h(AssignCustomerToSaleUseCase(auth).execute),
        "quick_create_customer": _h(
            QuickCreateCustomerForSaleUseCase(customer_auth).execute),
        "scan_loyalty_card": _h(ScanLoyaltyCardForSaleUseCase(auth).execute),
        "redeem_loyalty_points": _h(RedeemLoyaltyPointsUseCase(auth).execute),
        "scan_code": _scan_code_handler(connection, auth),
        "apply_sale_discount": _h(ApplySaleDiscountUseCase(auth).execute),
        "apply_line_discount": _h(ApplyLineDiscountUseCase(auth).execute),
        "record_payment": _payment_handler(connection, auth),
        "begin_checkout": _h(BeginSaleCheckoutUseCase(auth).execute),
        "checkout_sale": _h(CheckoutSaleUseCase(auth).execute),
        "suspend_sale": _h(SuspendSaleUseCase(auth).execute),
        "resume_sale": _h(ResumeSaleUseCase(auth).execute),
        "cancel_sale": _h(CancelSaleUseCase(auth).execute),
        "return_line": _h(ReturnSaleLineUseCase(auth).execute),
        "reverse_sale": _h(ReverseSaleUseCase(auth).execute),
        "request_invoice": _h(RequestInvoiceUseCase(auth).execute),
        "reprint_receipt": _reprint_handler(connection, auth, printer_service),
    }

    return SalesPosPresenter(
        session_context=session_context, query_services=query_services,
        command_handlers=command_handlers)


def _scan_code_handler(connection, auth):
    router = ScanCodeRouter(auth)

    def handler(*, sale_id, code, context, branch_id, actor_user_id, operation_id):
        return router.route(
            connection, sale_id=sale_id, code=code, context=ScanContext(context),
            branch_id=branch_id, actor_user_id=actor_user_id, operation_id=operation_id)
    return handler


def _payment_handler(connection, auth):
    run = RecordSalePaymentUseCase(auth).execute

    def handler(*, sale_id, method, amount, actor_user_id, operation_id, reference=None):
        return run(
            connection, sale_id=sale_id, method=method, amount=amount,
            actor_user_id=actor_user_id, operation_id=operation_id, reference=reference)
    return handler


def _reprint_handler(connection, auth, printer_service):
    run = ReprintReceiptUseCase(auth).execute

    def handler(**kwargs):
        return run(connection, printer_service, **kwargs)
    return handler


def create_sales_pos_view(connection, session_context=None, printer_service=None, parent=None):
    """Factory used by `modulos/ventas_pos.py`. Never receives the
    container itself — only what it needs, already unwrapped."""
    from frontend.desktop.modules.sales_pos.sales_pos_workspace import SalesPosWorkspace

    presenter = build_sales_pos_presenter(connection, session_context, printer_service)
    return SalesPosWorkspace(presenter, parent)
