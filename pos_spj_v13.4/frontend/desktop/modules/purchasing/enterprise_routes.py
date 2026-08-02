"""Composition root for the enterprise procurement UI.

The only place that touches the connection to wire read/analytics services and
use cases. The view/pages never see the connection nor the AppContainer.
"""

from __future__ import annotations

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
    ApprovePurchaseOrderUseCase,
    ChangePurchaseOrderUseCase,
    CreatePurchaseOrderUseCase,
    ReceivePurchaseOrderUseCase,
    SendPurchaseOrderUseCase,
)
from backend.application.procurement.use_cases.requisition_use_cases import (
    ApprovePurchaseRequisitionUseCase,
    CreatePurchaseRequisitionUseCase,
    SubmitPurchaseRequisitionUseCase,
)
<<<<<<< HEAD
from backend.application.procurement.use_cases.quotation_use_cases import CreateRfqUseCase
=======
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
from backend.application.procurement.use_cases.supplier_invoice_use_cases import (
    CaptureSupplierInvoiceUseCase,
    MatchSupplierInvoiceUseCase,
    ReleaseInvoiceVarianceUseCase,
)
from frontend.desktop.modules.purchasing.enterprise_presenter import (
    EnterprisePurchasingPresenter,
)


def _post_commit_dispatcher(connection):
    """Publish the procurement outbox to the app bus after a successful mutation."""
    def _dispatch():
        from backend.application.procurement.integrations.procurement_outbox_dispatcher import (
            dispatch_procurement_outbox,
        )
        from core.events.event_bus import get_bus
        dispatch_procurement_outbox(connection, get_bus())
    return _dispatch


<<<<<<< HEAD
def build_enterprise_presenter(connection, session_context=None,
                               origin_workspace=None) -> EnterprisePurchasingPresenter:
=======
def build_enterprise_presenter(connection, session_context=None) -> EnterprisePurchasingPresenter:
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
    authorization = PurchaseAuthorizationPolicy(
        ProcurementSessionPermissionChecker(session_context))
    supplier_directory = SupplierDirectoryQueryService(connection)
    tolerance_settings = ProcurementToleranceSettingsQueryService(connection)
    return EnterprisePurchasingPresenter(
        connection_provider=lambda: connection,
        read_services={
            "requisitions": RequisitionReadService(connection),
            "orders": OrderReadService(connection),
            "invoices": InvoiceReadService(connection),
            "receipts": ReceiptReadService(connection),
            "suppliers": supplier_directory,
        },
        analytics=ProcurementAnalyticsService(connection),
        event_dispatcher=_post_commit_dispatcher(connection),
        use_cases={
            "req_create": CreatePurchaseRequisitionUseCase(authorization),
            "req_submit": SubmitPurchaseRequisitionUseCase(authorization),
            "req_approve": ApprovePurchaseRequisitionUseCase(authorization),
<<<<<<< HEAD
            "rfq_create": CreateRfqUseCase(authorization, supplier_directory),
=======
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
            "po_create": CreatePurchaseOrderUseCase(authorization, supplier_directory),
            "po_approve": ApprovePurchaseOrderUseCase(authorization),
            "po_send": SendPurchaseOrderUseCase(authorization),
            "po_change": ChangePurchaseOrderUseCase(authorization),
            "po_receive": ReceivePurchaseOrderUseCase(authorization=authorization),
            "inv_capture": CaptureSupplierInvoiceUseCase(
                authorization, supplier_directory),
            "inv_match": MatchSupplierInvoiceUseCase(
                authorization, tolerance_settings=tolerance_settings),
            "inv_release": ReleaseInvoiceVarianceUseCase(authorization),
        },
        session_context=session_context,
        logistics_reads=LogisticsShipmentQueryService(connection),
        warehouse_directory=WarehouseDirectoryQueryService(connection),
        history_reads=PurchaseHistoryReadService(connection),
        origin_workspace=origin_workspace,
    )


def create_enterprise_purchasing_view(container, parent=None):
    from frontend.desktop.modules.purchasing.direct_purchase_routes import (
        build_direct_purchase_presenter,
    )
    from frontend.desktop.modules.purchasing.direct_purchase_view import (
        DirectPurchaseCreateView, DirectPurchaseHistoryView,
    )
    from frontend.desktop.modules.purchasing.enterprise_view import (
        EnterprisePurchasingView,
    )

    connection = getattr(container, "db", None) or getattr(container, "db_conn", None) \
        or container
    session_context = getattr(container, "session", None)
<<<<<<< HEAD
    origin_workspace = None
    logistics_service = getattr(container, "logistics_application_service", None)
    if logistics_service is not None:
        from backend.application.logistics.origin_purchase_workspace import (
            OriginPurchaseWorkspaceService,
        )
        shipment_queries = getattr(container, "logistics_shipment_queries", None)
        if shipment_queries is None:
            raise RuntimeError("LogisticsShipmentQueryService no está configurado")
        origin_workspace = OriginPurchaseWorkspaceService(
            logistics_service, shipment_queries)
    presenter = build_enterprise_presenter(connection, session_context, origin_workspace)
    direct_presenter = build_direct_purchase_presenter(connection, session_context)
    direct_views = {
        "create": DirectPurchaseCreateView(direct_presenter),
        "history": DirectPurchaseHistoryView(direct_presenter),
    }
    return EnterprisePurchasingView(presenter, parent, direct_purchase_views=direct_views)
=======
    presenter = build_enterprise_presenter(connection, session_context)
    direct_view = DirectPurchaseView(
        build_direct_purchase_presenter(connection, session_context))
    return EnterprisePurchasingView(presenter, parent, direct_purchase_view=direct_view)
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
