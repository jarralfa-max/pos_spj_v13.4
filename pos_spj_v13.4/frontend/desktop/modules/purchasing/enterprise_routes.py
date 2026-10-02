"""Composition root for the enterprise procurement UI.

The only place that touches the connection to wire read/analytics services and
use cases. The view/pages never see the connection nor the AppContainer.
"""

from __future__ import annotations

import logging

from backend.application.procurement.adapters.product_catalog_adapter import (
    ProcurementProductCatalogAdapter,
)
from backend.application.procurement.adapters.supplier_profile_adapter import (
    InventoryReceiptStatusAdapter,
    SupplierFinanceAdapter,
    SupplierProfileAdapter,
)
from backend.application.procurement.queries import SupplierPickerQueryService
from backend.application.procurement.queries.enterprise_read_services import (
    InvoiceReadService,
    ReceiptReadService,
    OrderReadService,
    RequisitionReadService,
)
from backend.application.procurement.queries.procurement_analytics_service import (
    ProcurementAnalyticsService,
)
from backend.application.procurement.queries.purchase_history_read_service import (
    PurchaseHistoryReadService,
)
from backend.application.procurement.queries.quotation_read_services import (
    RfqReadService,
)
from backend.application.logistics.queries import LogisticsShipmentQueryService
from backend.application.logistics.warehouse_directory import WarehouseDirectoryQueryService
from backend.application.procurement.queries.supplier_directory_query_service import (
    SupplierDirectoryQueryService,
)
from backend.application.procurement.queries.tolerance_settings_query_service import (
    ProcurementToleranceSettingsQueryService,
)
from backend.application.procurement.authorization import PurchaseAuthorizationPolicy
from backend.application.procurement.session_authorization import (
    ProcurementSessionPermissionChecker,
)
from backend.application.procurement.use_cases.purchase_order_use_cases import (
    AcknowledgePurchaseOrderUseCase,
    ApprovePurchaseOrderUseCase,
    ChangePurchaseOrderUseCase,
    CreatePurchaseOrderUseCase,
    ReceivePurchaseOrderUseCase,
    SendPurchaseOrderUseCase,
)
from backend.application.procurement.use_cases.direct_purchase_use_cases import (
    ReceiveDirectPurchaseUseCase,
)
from backend.application.procurement.use_cases.requisition_use_cases import (
    ApprovePurchaseRequisitionUseCase,
    CreatePurchaseRequisitionUseCase,
    SubmitPurchaseRequisitionUseCase,
)
from backend.application.procurement.use_cases.quotation_use_cases import (
    AwardSupplierQuoteUseCase,
    CaptureSupplierQuoteUseCase,
    CreateRfqUseCase,
)
from backend.application.procurement.use_cases.supplier_invoice_use_cases import (
    CaptureSupplierInvoiceUseCase,
    MatchSupplierInvoiceUseCase,
    ReleaseInvoiceVarianceUseCase,
)
from frontend.desktop.modules.purchasing.enterprise_presenter import (
    EnterprisePurchasingPresenter,
)


logger = logging.getLogger("spj.purchasing.enterprise_routes")


def _post_commit_dispatcher(connection):
    """Publish the procurement outbox to the app bus after a successful mutation."""
    def _dispatch():
        from backend.application.procurement.integrations.procurement_outbox_dispatcher import (
            dispatch_procurement_outbox,
        )
        from backend.shared.events.application_bus import get_bus
        dispatch_procurement_outbox(connection, get_bus())
    return _dispatch


def build_enterprise_presenter(connection, session_context=None, *,
                               logistics_service=None,
                               logistics_queries=None) -> EnterprisePurchasingPresenter:
    authorization = PurchaseAuthorizationPolicy(
        ProcurementSessionPermissionChecker(session_context))
    supplier_directory = SupplierDirectoryQueryService(connection)
    tolerance_settings = ProcurementToleranceSettingsQueryService(connection)
    # Días de crédito del proveedor -> vencimiento de la cuenta por pagar.
    from backend.application.procurement.adapters.supplier_payment_terms_adapter import (
        SupplierPaymentTermsAdapter,
    )
    payment_terms = SupplierPaymentTermsAdapter(connection)
    # Reuse the canonical Logistics wiring built once at app startup
    # (core/events/wiring.py::_wire_logistics_pipeline) instead of constructing a
    # second, repository-less LogisticsShipmentQueryService here.
    logistics_reads = logistics_queries or LogisticsShipmentQueryService(connection)
    product_catalog = ProcurementProductCatalogAdapter(connection)
    from backend.application.suppliers.queries.supplier_origin_query_service import (
        SupplierOriginQueryService,
    )
    supplier_origins = SupplierOriginQueryService(connection)
    warehouse_directory = WarehouseDirectoryQueryService(connection)
    create_order = CreatePurchaseOrderUseCase(
        authorization, supplier_directory, product_catalog=product_catalog,
        warehouse_directory=warehouse_directory, supplier_origins=supplier_origins)
    from backend.application.procurement.use_cases.award_order_use_cases import (
        GeneratePurchaseOrdersFromAwardUseCase,
    )
    # Logística: nadie la construía en producción desde que se borró
    # `core/events/wiring.py`; «Compra en origen» quedaba siempre apagada.
    if logistics_service is None or logistics_queries is None:
        from backend.application.logistics.composition import build_logistics_services
        logistics_service, logistics_queries = build_logistics_services(
            connection, session_context)
        logistics_reads = logistics_queries
    from backend.application.logistics.origin_purchase_workspace import (
        OriginPurchaseWorkspaceService,
    )
    receive_order_uc = ReceivePurchaseOrderUseCase(authorization=authorization,
                                                   product_catalog=product_catalog)
    # Un SOLO punto de publicación: el despachador del presentador (el mismo
    # que usan todas las demás operaciones). Antes la recepción en origen
    # publicaba por su cuenta en el bus global.
    presenter_ref: list = []
    receive_direct_uc = ReceiveDirectPurchaseUseCase(authorization,
                                                     warehouse_directory=warehouse_directory,
                                                     product_catalog=product_catalog)

    def _publish(result) -> None:
        dispatch = getattr(presenter_ref[0], "_dispatch", None) if presenter_ref else None
        if result.success and dispatch is not None:
            try:
                dispatch()
            except Exception:  # pragma: no cover - el outbox se reintenta después
                logger.exception("post-commit dispatch failed (recepción en origen)")

    def receive_direct(*, actor_user_id, order_id, lines, shipment_id, operation_id):
        result = receive_direct_uc.execute(
            connection, actor_user_id=actor_user_id, direct_purchase_id=order_id,
            operation_id=operation_id, receipt_lines=lines, shipment_id=shipment_id)
        _publish(result)
        return result.success, result.message, dict(result.data,
                                                    entity_id=result.entity_id)

    def receive_order(*, actor_user_id, order_id, lines, shipment_id, operation_id):
        result = receive_order_uc.execute(
            connection, actor_user_id=actor_user_id, purchase_order_id=order_id,
            operation_id=operation_id, receipt_lines=lines, shipment_id=shipment_id)
        _publish(result)
        return result.success, result.message, dict(result.data,
                                                     entity_id=result.entity_id)

    origin_workspace = OriginPurchaseWorkspaceService(
        logistics_service, logistics_queries, connection=connection,
        supplier_origins=supplier_origins, product_catalog=product_catalog,
        receive_order=receive_order, receive_direct=receive_direct)
    presenter = EnterprisePurchasingPresenter(
        connection_provider=lambda: connection,
        read_services={
            "requisitions": RequisitionReadService(connection),
            "orders": OrderReadService(connection),
            "invoices": InvoiceReadService(connection),
            "receipts": ReceiptReadService(connection),
            "rfqs": RfqReadService(connection),
        },
        analytics=ProcurementAnalyticsService(connection),
        event_dispatcher=_post_commit_dispatcher(connection),
        use_cases={
            "req_create": CreatePurchaseRequisitionUseCase(authorization),
            "req_submit": SubmitPurchaseRequisitionUseCase(authorization),
            "req_approve": ApprovePurchaseRequisitionUseCase(authorization),
            "rfq_create": CreateRfqUseCase(authorization, supplier_directory),
            "quote_capture": CaptureSupplierQuoteUseCase(authorization, supplier_directory),
            "quote_award": AwardSupplierQuoteUseCase(authorization),
            "po_create": create_order,
            "po_from_award": GeneratePurchaseOrdersFromAwardUseCase(create_order, authorization),
            "po_approve": ApprovePurchaseOrderUseCase(authorization),
            "po_send": SendPurchaseOrderUseCase(authorization),
            "po_acknowledge": AcknowledgePurchaseOrderUseCase(authorization),
            "po_change": ChangePurchaseOrderUseCase(authorization),
            "po_receive": ReceivePurchaseOrderUseCase(authorization=authorization,
                                                      product_catalog=product_catalog),
            "inv_capture": CaptureSupplierInvoiceUseCase(
                authorization, supplier_directory),
            "inv_match": MatchSupplierInvoiceUseCase(
                authorization, tolerance_settings=tolerance_settings,
                payment_terms=payment_terms),
            "inv_release": ReleaseInvoiceVarianceUseCase(
                authorization, payment_terms=payment_terms),
        },
        session_context=session_context,
        logistics_reads=logistics_reads,
        warehouse_directory=warehouse_directory,
        history_reads=PurchaseHistoryReadService(connection),
        origin_workspace=origin_workspace,
        supplier_picker=SupplierPickerQueryService(connection),
        product_catalog=product_catalog,
        supplier_origins=supplier_origins,
        supplier_profile=SupplierProfileAdapter(connection),
        supplier_finance=SupplierFinanceAdapter(connection),
        receipt_status=InventoryReceiptStatusAdapter(connection),
    )
    presenter_ref.append(presenter)
    return presenter


def create_enterprise_purchasing_view(container, parent=None):
    from frontend.desktop.modules.purchasing.direct_purchase_routes import (
        build_direct_purchase_presenter,
    )
    from frontend.desktop.modules.purchasing.direct_purchase_view import (
        DirectPurchaseCreateView,
        DirectPurchaseHistoryView,
    )
    from frontend.desktop.modules.purchasing.enterprise_view import (
        EnterprisePurchasingView,
    )

    connection = getattr(container, "db", None) or getattr(container, "db_conn", None) \
        or container
    session_context = getattr(container, "session", None)
    logistics_service = getattr(container, "logistics_application_service", None)
    logistics_queries = getattr(container, "logistics_shipment_queries", None)
    presenter = build_enterprise_presenter(
        connection, session_context,
        logistics_service=logistics_service, logistics_queries=logistics_queries)
    direct_presenter = build_direct_purchase_presenter(connection, session_context)
    direct_views = {
        "create": DirectPurchaseCreateView(direct_presenter),
        "history": DirectPurchaseHistoryView(direct_presenter),
    }
    return EnterprisePurchasingView(presenter, parent, direct_purchase_views=direct_views)
