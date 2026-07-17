"""Composition root for the enterprise procurement UI.

The only place that touches the connection to wire read/analytics services and
use cases. The view/pages never see the connection nor the AppContainer.
"""

from __future__ import annotations

from backend.application.procurement.queries.enterprise_read_services import (
    InvoiceReadService,
    OrderReadService,
    RequisitionReadService,
)
from backend.application.procurement.queries.procurement_analytics_service import (
    ProcurementAnalyticsService,
)
from backend.application.procurement.queries.purchase_history_read_service import (
    PurchaseHistoryReadService,
)
from backend.application.procurement.queries.qr_traceability_read_service import (
    QrTraceabilityReadService,
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
from backend.application.procurement.use_cases.qr_container_use_cases import (
    AssignQrContainerUseCase,
    RegisterQrContainerUseCase,
)
from backend.application.procurement.use_cases.qr_reception_use_cases import (
    CompleteQrReceptionUseCase,
)
from backend.application.procurement.use_cases.supplier_invoice_use_cases import (
    CaptureSupplierInvoiceUseCase,
    MatchSupplierInvoiceUseCase,
    ReleaseInvoiceVarianceUseCase,
)
from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema
from frontend.desktop.modules.purchasing.enterprise_presenter import (
    EnterprisePurchasingPresenter,
)


def _post_commit_dispatcher(connection):
    """Publish the procurement outbox to the app bus after a successful mutation."""
    def _dispatch():
        try:
            from backend.application.procurement.integrations.procurement_outbox_dispatcher import (
                dispatch_procurement_outbox,
            )
            from core.events.event_bus import get_bus
            dispatch_procurement_outbox(connection, get_bus())
        except Exception:
            pass  # best-effort; a pending outbox row is retried next time
    return _dispatch


def build_enterprise_presenter(connection, session_context=None) -> EnterprisePurchasingPresenter:
    create_procurement_schema(connection)  # idempotent bootstrap
    return EnterprisePurchasingPresenter(
        connection_provider=lambda: connection,
        read_services={
            "requisitions": RequisitionReadService(connection),
            "orders": OrderReadService(connection),
            "invoices": InvoiceReadService(connection),
        },
        analytics=ProcurementAnalyticsService(connection),
        event_dispatcher=_post_commit_dispatcher(connection),
        use_cases={
            "req_create": CreatePurchaseRequisitionUseCase(),
            "req_submit": SubmitPurchaseRequisitionUseCase(),
            "req_approve": ApprovePurchaseRequisitionUseCase(),
            "po_create": CreatePurchaseOrderUseCase(),
            "po_approve": ApprovePurchaseOrderUseCase(),
            "po_send": SendPurchaseOrderUseCase(),
            "po_change": ChangePurchaseOrderUseCase(),
            "po_receive": ReceivePurchaseOrderUseCase(),
            "inv_capture": CaptureSupplierInvoiceUseCase(),
            "inv_match": MatchSupplierInvoiceUseCase(),
            "inv_release": ReleaseInvoiceVarianceUseCase(),
            "qr_register": RegisterQrContainerUseCase(),
            "qr_assign": AssignQrContainerUseCase(),
            "qr_receive": CompleteQrReceptionUseCase(),
        },
        session_context=session_context,
        qr_reads=QrTraceabilityReadService(connection),
        history_reads=PurchaseHistoryReadService(connection),
    )


def create_enterprise_purchasing_view(container, parent=None):
    from frontend.desktop.modules.purchasing.direct_purchase_routes import (
        build_direct_purchase_presenter,
    )
    from frontend.desktop.modules.purchasing.direct_purchase_view import (
        DirectPurchaseView,
    )
    from frontend.desktop.modules.purchasing.enterprise_view import (
        EnterprisePurchasingView,
    )

    connection = getattr(container, "db", None) or getattr(container, "db_conn", None) \
        or container
    session_context = getattr(container, "session_context", None)
    presenter = build_enterprise_presenter(connection, session_context)
    direct_view = DirectPurchaseView(
        build_direct_purchase_presenter(connection, session_context))
    return EnterprisePurchasingView(presenter, parent, direct_purchase_view=direct_view)
