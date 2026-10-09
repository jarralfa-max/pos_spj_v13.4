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
    ApplySaleDiscountPercentUseCase,
    ApplySaleDiscountUseCase,
)
from backend.application.sales.use_cases.invoice_use_cases import RequestInvoiceUseCase
from backend.application.sales.use_cases.lifecycle_use_cases import (
    BeginSaleCheckoutUseCase,
    CancelSaleUseCase,
    ResumeSaleUseCase,
    SuspendSaleUseCase,
)
from backend.application.sales.use_cases.coupon_use_cases import (
    ApplyCouponToSaleUseCase,
    RemoveCouponFromSaleUseCase,
    SellPrepaidVoucherUseCase,
)
from backend.application.sales.use_cases.loyalty_use_cases import RedeemLoyaltyPointsUseCase
from backend.application.sales.use_cases.payment_use_cases import RecordSalePaymentUseCase
from backend.application.sales.use_cases.receipt_use_cases import (
    PrintSaleReceiptUseCase,
    ReprintReceiptUseCase,
)
from backend.application.sales.use_cases.return_use_cases import ReturnSaleLineUseCase, ReverseSaleUseCase
from backend.application.sales.use_cases.scan_use_cases import ScanCodeRouter
from backend.domain.sales.enums import ScanContext
from backend.infrastructure.integrations.sales_customer_display_client import SalesCustomerDisplayClient
from backend.infrastructure.integrations.sales_pricing_client import SalesPricingClient
from frontend.desktop.modules.sales_pos.sales_pos_presenter import SalesPosPresenter


def _after_commit(handler, connection):
    """Tras un cobro, cancelación, devolución o reverso exitoso, entrega
    `sales_outbox` al bus de la aplicación (Finanzas asienta, Fidelidad acredita,
    retira o devuelve el canje). Mismo patrón que Compras
    (`direct_purchase_routes._post_commit_dispatcher`). Un fallo aquí no
    deshace la operación: el evento queda pendiente y sale en el siguiente
    despacho. Hasta el 2026-10-02 sólo el cobro despachaba: el asiento de una
    devolución esperaba a la siguiente venta."""
    def run(**kwargs):
        result = handler(**kwargs)
        if getattr(result, "success", False):
            # Antes del despacho: un vale recién emitido debe tener su obligación
            # para que la venta pagada con él se pueda asentar (2026-10-03).
            from backend.application.loyalty.integrations.finance_posting import (
                post_loyalty_finance as _antes,
            )
            _antes(connection)
            try:
                from backend.application.sales.integrations.wiring import dispatch_sales_outbox
                from backend.shared.events.application_bus import get_bus
                dispatch_sales_outbox(connection, get_bus())
            except Exception:
                import logging
                logging.getLogger("spj.sales_pos.composition").exception(
                    "despacho de sales_outbox fallido")
            # Fidelidad → Finanzas (2026-10-03): los puntos que la venta acumuló,
            # canjeó o devolvió llegan a contabilidad. Nunca propaga.
            from backend.application.loyalty.integrations.finance_posting import (
                post_loyalty_finance,
            )
            post_loyalty_finance(connection)
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


def _open_drawer_after_cash_sale(handler, connection, session_context):
    """«Cajón con venta» (CASH-26, 2026-10-07): un cobro con efectivo abre el
    cajón del turno por el pulso de la impresora del ticket. Hasta hoy el POS
    nunca abría el cajón. Un cajón que no responde no deshace la venta: Caja
    registra la falla (`CASH_HARDWARE_OPERATION_FAILED`) y alerta."""
    def run(**kwargs):
        result = handler(**kwargs)
        if not getattr(result, "success", False):
            return result
        try:
            from backend.application.cash_register.authorization import CashAuthorizationPolicy
            from backend.application.cash_register.session_authorization import (
                CashSessionBranchScopeChecker,
                CashSessionPermissionChecker,
            )
            from backend.infrastructure.hardware.cash_drawer_gateway import (
                PrinterKickCashDrawerGateway,
            )
            from backend.infrastructure.integrations.sales_cash_drawer_client import (
                SalesCashDrawerGateway,
            )
            from backend.shared.ids import new_uuid

            policy = CashAuthorizationPolicy(
                permissions=CashSessionPermissionChecker(session_context),
                scopes=CashSessionBranchScopeChecker(session_context))
            gateway = PrinterKickCashDrawerGateway(
                connection,
                workstation_id=getattr(session_context, "workstation_id", None) or None)
            SalesCashDrawerGateway(policy, gateway).open_for_cash_sale(
                connection, sale_id=kwargs["sale_id"],
                branch_id=getattr(session_context, "active_branch_id", None),
                actor_user_id=kwargs["actor_user_id"], operation_id=new_uuid())
            connection.commit()
        except Exception:  # noqa: BLE001 - la venta ya está cobrada
            import logging
            logging.getLogger("spj.sales_pos.composition").exception(
                "no se pudo abrir el cajón tras el cobro")
        return result
    return run


def _cash_refund_service(connection, session_context):
    """Reembolso de devoluciones en Caja (decisión del usuario 2026-10-02).

    Dos personas: quien devuelve (sesión, `CAJA.reembolso.solicitar`) y quien
    autoriza (otro usuario, `CAJA.reembolso.autorizar`, resuelto contra
    `rol_permisos`). Tope: `cash_operation_limits` de tipo REFUND."""
    from backend.application.cash_register.authorization import CashAuthorizationPolicy
    from backend.application.cash_register.refund_integration import CashRefundIntegrationService
    from backend.application.cash_register.session_authorization import (
        CashSessionBranchScopeChecker,
        CashSessionPermissionChecker,
    )
    from backend.application.security.authorizer_permission_checker import (
        AuthorizerPermissionChecker,
    )
    from backend.application.security.session_or_authorizer_checker import (
        SessionOrAuthorizerBranchScopeChecker,
        SessionOrAuthorizerPermissionChecker,
    )
    from backend.infrastructure.db.repositories.cash_register.operation_limits import (
        cash_limit_policy,
    )

    branch_id = getattr(session_context, "active_branch_id", None) or None
    policy = CashAuthorizationPolicy(
        permissions=SessionOrAuthorizerPermissionChecker(
            session=session_context,
            session_checker=CashSessionPermissionChecker(session_context),
            authorizer_checker=AuthorizerPermissionChecker(connection, branch_id=branch_id)),
        scopes=SessionOrAuthorizerBranchScopeChecker(
            session=session_context,
            session_scopes=CashSessionBranchScopeChecker(session_context)))

    class _Lazy:
        """El tope se lee al reembolsar, no al abrir el POS: un cambio en Caja
        aplica sin reabrir la pantalla (y una base sin Caja no impide abrirla)."""

        def process(self, connection, **kwargs):
            return CashRefundIntegrationService(
                policy, cash_limit_policy(connection, "REFUND")).process(connection, **kwargs)

    return _Lazy()


def _loyalty_summary(connection):
    from backend.infrastructure.integrations.sales_loyalty_client import SalesLoyaltyClient

    return SalesLoyaltyClient(connection)


def _prepaid_definitions(connection):
    def consulta() -> list[dict]:
        from backend.infrastructure.integrations.sales_instruments_client import (
            SalesInstrumentsClient,
        )

        return SalesInstrumentsClient(connection).prepaid_definitions()

    return consulta


def _voucher_balance(connection):
    def consulta(*, code: str) -> dict:
        from backend.infrastructure.integrations.sales_instruments_client import (
            SalesInstrumentsClient,
        )

        return SalesInstrumentsClient(connection).voucher_balance(code=code)

    return consulta


def _points_to_earn(connection):
    """Puntos que daría la venta con las REGLAS de Fidelidad (§13, 2026-10-03):
    el mismo evaluador que acredita al cobrar, con los productos, la sucursal,
    el canal y el cliente de la venta. Se leen al calcular: una regla activada
    aplica sin reabrir el POS. El crédito se desconoce hasta cobrar."""
    def estimate(*, sale=None, total=None) -> int:
        from backend.application.loyalty.queries.customer_benefits_query import (
            LoyaltyAccrualEvaluator,
        )

        if sale is None:
            return LoyaltyAccrualEvaluator(connection).evaluate(
                customer_id=None, branch_id=None, total=total).points
        return LoyaltyAccrualEvaluator(connection).evaluate(
            customer_id=sale.customer_id, branch_id=sale.branch_id, total=sale.total,
            channel=str(getattr(sale, "channel", "") or "POS"),
            lines=[{"product_id": ln.product_id, "quantity": str(ln.quantity),
                    "amount": str(ln.line_total)} for ln in sale.lines]).points

    return estimate


def _cash_tender(*, total, received):
    from backend.domain.sales.policies.payment_policy import CashPaymentPolicy

    return CashPaymentPolicy.evaluate(total=total, received=received)


def _payment_amount_check(*, method, amount, outstanding):
    from backend.domain.sales.enums import PaymentMethod
    from backend.domain.sales.exceptions import PaymentExceedsBalanceError
    from backend.domain.sales.policies.payment_policy import SalePaymentPolicy

    try:
        SalePaymentPolicy.ensure_amount_allowed(
            method=PaymentMethod(method), amount=amount, outstanding=outstanding)
    except PaymentExceedsBalanceError as exc:
        return str(exc)
    return None


def _weight_policy(weight):
    from backend.domain.sales.exceptions import InvalidWeightError
    from backend.domain.sales.policies.line_policies import WeightPolicy

    try:
        return WeightPolicy.ensure_valid(weight), ""
    except InvalidWeightError as exc:
        return None, str(exc)


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
    # El ticket sale por la impresora que Document Output asigna a la sucursal.
    # Antes el shell pasaba `printer_service=None` y el POS no imprimía nada.
    printer = printer_service or _sales_ticket_printer(connection, session_context)
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
        # Saldo y nivel del cliente (lectura sin efectos de Fidelidad, §23).
        "loyalty_summary": _loyalty_summary(connection),
        "points_to_earn": _points_to_earn(connection),
        "voucher_balance": _voucher_balance(connection),
        "prepaid_voucher_definitions": _prepaid_definitions(connection),
        "pricing": pricing_client,
        # Prueba quién autoriza con su usuario y clave (mismas reglas y
        # bloqueo que el login); el permiso lo decide el caso de uso.
        "authorizer_credentials": _authorizer_credentials(connection).execute,
        # Turno de caja abierto del cajero (Fase 6: sin turno no se cobra).
        "cash_shift": _cash_shift_problem(connection),
        # Reglas puras del dominio que la pantalla consulta (cambio, peso).
        "cash_tender": _cash_tender,
        "payment_amount_check": _payment_amount_check,
        "weight_policy": _weight_policy,
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
        "apply_coupon": _h(ApplyCouponToSaleUseCase(auth).execute),
        "remove_coupon": _h(RemoveCouponFromSaleUseCase(auth).execute),
        "sell_prepaid_voucher": _h(SellPrepaidVoucherUseCase(auth).execute),
        "scan_code": _scan_code_handler(connection, auth),
        "apply_sale_discount": _h(ApplySaleDiscountUseCase(
            auth, authorizer_authorization=authorizer_auth,
            minimum_prices=pricing_client).execute),
        "apply_sale_discount_percent": _h(ApplySaleDiscountPercentUseCase(
            auth, authorizer_authorization=authorizer_auth,
            minimum_prices=pricing_client).execute),
        "apply_line_discount": _h(ApplyLineDiscountUseCase(
            auth, authorizer_authorization=authorizer_auth,
            minimum_prices=pricing_client).execute),
        "record_payment": _payment_handler(connection, auth, customer_auth),
        "begin_checkout": _h(BeginSaleCheckoutUseCase(auth).execute),
        "checkout_sale": _open_drawer_after_cash_sale(_after_commit(_h(CheckoutSaleUseCase(
            auth, inventory_auth, authorizer_authorization=authorizer_auth,
            costs=pricing_client).execute), connection), connection, session_context),
        "suspend_sale": _h(SuspendSaleUseCase(auth, inventory_auth).execute),
        "resume_sale": _h(ResumeSaleUseCase(auth).execute),
        "cancel_sale": _after_commit(
            _h(CancelSaleUseCase(auth, inventory_auth).execute), connection),
        "return_line": _after_commit(_h(ReturnSaleLineUseCase(
            auth, inventory_auth, authorizer_authorization=authorizer_auth,
            cash_refund_service=_cash_refund_service(connection, session_context)).execute),
            connection),
        "reverse_sale": _after_commit(_h(ReverseSaleUseCase(
            auth, inventory_auth, authorizer_authorization=authorizer_auth).execute),
            connection),
        "request_invoice": _h(RequestInvoiceUseCase(auth).execute),
        "print_receipt": _receipt_handler(PrintSaleReceiptUseCase(auth), connection, printer),
        "reprint_receipt": _receipt_handler(ReprintReceiptUseCase(auth), connection, printer),
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


def _receipt_handler(use_case, connection, printer):
    run = use_case.execute

    def handler(**kwargs):
        return run(connection, printer, **kwargs)
    return handler


def _sales_ticket_printer(connection, session_context):
    from backend.infrastructure.hardware.sales_ticket_printer import SalesTicketPrinter

    return SalesTicketPrinter(
        connection, branch_id=getattr(session_context, "active_branch_id", None) or None)


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
