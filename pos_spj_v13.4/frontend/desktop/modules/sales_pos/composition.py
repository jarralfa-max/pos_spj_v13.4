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
SALES-N phase didn't already build and test. As of SALES-22 the legacy
`modulos/ventas.py` was deleted; this is the only live POS screen (this
docstring previously claimed otherwise — verify wiring claims like that
against `frontend/desktop/shell/desktop_shell_window_composition.py`
directly, not comments, since they go stale).
"""

from __future__ import annotations

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.queries.customer_lookup_query_service import (
    CustomerLookupQueryService,
)
from backend.application.customers.session_authorization import CustomerSessionPermissionChecker
from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.session_authorization import (
    InventorySessionPermissionChecker,
)
from backend.application.sales.authorization import SalesAuthorizationPolicy
from backend.application.sales.queries.benefit_evaluation_service import SaleBenefitEvaluationService
from backend.application.customer_display.queries.advertising_query_service import AdvertisingQueryService
from backend.application.customer_display.use_cases.record_content_impression_use_case import (
    RecordContentImpressionUseCase,
)
from backend.application.sales.queries.catalog_query_service import SalesCatalogQueryService
from backend.application.sales.queries.customer_display_query_service import CustomerDisplayQueryService
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
from backend.infrastructure.integrations.sales_customer_display_client import SalesCustomerDisplayClient
from backend.infrastructure.integrations.sales_pricing_client import SalesPricingClient
from frontend.desktop.modules.sales_pos.sales_pos_presenter import SalesPosPresenter


def _after_commit(handler, connection):
    """Tras un cobro exitoso, entrega `sales_outbox` al bus de la aplicación
    (Finanzas asienta la venta). Mismo patrón que Compras
    (`direct_purchase_routes._post_commit_dispatcher`). Un fallo aquí no
    deshace la venta: el evento queda pendiente y sale en el siguiente cobro."""
    def run(**kwargs):
        result = handler(**kwargs)
        if getattr(result, "success", False):
            try:
                from backend.application.sales.integrations.wiring import dispatch_sales_outbox
                from backend.shared.events.application_bus import get_bus
                dispatch_sales_outbox(connection, get_bus())
            except Exception:
                import logging
                logging.getLogger("spj.sales_pos.composition").exception(
                    "despacho de sales_outbox fallido")
        return result
    return run


def _cash_shift_problem(connection):
    def check(*, branch_id: str, cashier_user_id: str) -> str | None:
        from backend.domain.cash_register.exceptions import CashRegisterError
        from backend.infrastructure.integrations.sales_cash_effects_client import (
            SalesCashEffectsClient,
        )
        import sqlite3
        try:
            SalesCashEffectsClient().require_open_shift(
                connection, branch_id=branch_id, cashier_user_id=cashier_user_id)
        except (CashRegisterError, sqlite3.OperationalError):
            return "No tienes un turno de caja abierto. Abre tu turno en Caja antes de cobrar."
        return None
    return check


def _authorizer_credentials(connection):
    from backend.security.authentication.verify_authorizer_credentials_use_case import (
        build_authorizer_credentials_verifier,
    )
    return build_authorizer_credentials_verifier(connection)


def build_sales_pos_presenter(
    connection, session_context=None, printer_service=None,
) -> SalesPosPresenter:
    checker = SalesSessionPermissionChecker(session_context)
    auth = SalesAuthorizationPolicy(checker)
    customer_auth = CustomerAuthorizationPolicy(CustomerSessionPermissionChecker(session_context))
    # Ventas retiene y suelta stock a traves del contexto de Inventario, y esas
    # operaciones exigen permisos `INVENTARIO.reserva.*` propios. Se construye
    # con el verificador REAL de la sesion (§23): sin esto, el cliente de
    # inventario cae en una politica que falla cerrada y el cobro se deniega.
    inventory_auth = InventoryAuthorizationPolicy(
        InventorySessionPermissionChecker(session_context))
    # El AUTORIZADOR de una excepción (descuento grande, bajo el mínimo) es
    # otro usuario: el verificador de sesión sólo responde por el cajero y lo
    # denegaba siempre. Mismo estándar que Precios.
    from backend.application.security.authorizer_permission_checker import (
        AuthorizerPermissionChecker,
    )
    authorizer_auth = SalesAuthorizationPolicy(AuthorizerPermissionChecker(
        connection, branch_id=getattr(session_context, "active_branch_id", None) or None))
    pricing_client = SalesPricingClient(connection)
    # El canje de puntos es de Fidelidad y exige sus propios permisos
    # (`GROWTH_ENGINE.puntos.canjear`), verificados contra la sesión real.
    from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
    from backend.application.loyalty.session_authorization import LoyaltySessionPermissionChecker
    loyalty_auth = LoyaltyAuthorizationPolicy(LoyaltySessionPermissionChecker(session_context))

    query_services = {
        "catalog": SalesCatalogQueryService(connection),
        "sale_query": SaleQueryService(connection, auth),
        "benefit_evaluation": SaleBenefitEvaluationService(connection, auth),
        "device_health": DeviceHealthQueryService(connection, auth),
        "customer_display": CustomerDisplayQueryService(connection, auth),
        "advertising": AdvertisingQueryService(connection),
        "customer_search": CustomerLookupQueryService(connection, customer_auth),
        "pricing": pricing_client,
        # Prueba quién autoriza con su usuario y clave (mismas reglas y
        # bloqueo que el login); el permiso lo decide el caso de uso.
        "authorizer_credentials": _authorizer_credentials(connection).execute,
        # Turno de caja abierto del cajero (Fase 6: sin turno no se cobra).
        "cash_shift": _cash_shift_problem(connection),
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
        "redeem_loyalty_points": _h(RedeemLoyaltyPointsUseCase(
            auth, loyalty_authorization=loyalty_auth).execute),
        "scan_code": _scan_code_handler(connection, auth),
        "apply_sale_discount": _h(ApplySaleDiscountUseCase(
            auth, authorizer_authorization=authorizer_auth,
            minimum_prices=pricing_client).execute),
        "apply_line_discount": _h(ApplyLineDiscountUseCase(
            auth, authorizer_authorization=authorizer_auth,
            minimum_prices=pricing_client).execute),
        "record_payment": _payment_handler(connection, auth, customer_auth),
        "begin_checkout": _h(BeginSaleCheckoutUseCase(auth).execute),
        "checkout_sale": _after_commit(_h(CheckoutSaleUseCase(
            auth, inventory_auth, authorizer_authorization=authorizer_auth,
            costs=pricing_client).execute), connection),
        "suspend_sale": _h(SuspendSaleUseCase(auth, inventory_auth).execute),
        "resume_sale": _h(ResumeSaleUseCase(auth).execute),
        "cancel_sale": _h(CancelSaleUseCase(auth, inventory_auth).execute),
        "return_line": _h(ReturnSaleLineUseCase(auth, inventory_auth).execute),
        "reverse_sale": _h(ReverseSaleUseCase(auth, inventory_auth).execute),
        "request_invoice": _h(RequestInvoiceUseCase(auth).execute),
        "reprint_receipt": _reprint_handler(connection, auth, printer_service),
        "push_customer_display": _customer_display_handler(connection),
        "record_ad_impression": _record_ad_impression_handler(connection),
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


def _payment_handler(connection, auth, customer_auth):
    """`customer_auth` se RECIBE; no estaba en el alcance de esta función.

    Lo introduje en `bf615bea` (PASS 3, crédito y CxC): añadí
    `customer_authorization=customer_auth` aquí, donde ese nombre sólo existe
    dentro de `build_sales_pos_presenter`. Y no era un fallo latente que
    esperara a que alguien cobrara — esta línea corre AL CONSTRUIR el
    diccionario de manejadores, así que `build_sales_pos_presenter` reventaba
    con `NameError` y el Punto de Venta no llegaba a abrirse.

    Una venta a crédito exige el permiso de crédito del contexto de Clientes,
    que es lo que esta política aporta; por eso se pasa en vez de quitarse.
    """
    run = RecordSalePaymentUseCase(auth, customer_authorization=customer_auth).execute

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


def _customer_display_handler(connection):
    client = SalesCustomerDisplayClient(connection)

    def handler(*, gateway, state, branch_id=None):
        client.push_sale_state(gateway, state=state, branch_id=branch_id)
    return handler


def _record_ad_impression_handler(connection):
    run = RecordContentImpressionUseCase(connection).execute

    def handler(*, placement_id, duration_shown_seconds):
        run(placement_id=placement_id, duration_shown_seconds=duration_shown_seconds)
    return handler


def create_sales_pos_view(connection, session_context=None, printer_service=None, parent=None):
    """Factory used by `modulos/ventas_pos.py`. Never receives the
    container itself — only what it needs, already unwrapped."""
    from frontend.desktop.modules.sales_pos.sales_pos_workspace import SalesPosWorkspace

    presenter = build_sales_pos_presenter(connection, session_context, printer_service)
    return SalesPosWorkspace(presenter, parent)
