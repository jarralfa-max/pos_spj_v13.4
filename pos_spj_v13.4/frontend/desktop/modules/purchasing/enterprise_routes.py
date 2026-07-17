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
from backend.application.procurement.use_cases.supplier_invoice_use_cases import (
    CaptureSupplierInvoiceUseCase,
    MatchSupplierInvoiceUseCase,
    ReleaseInvoiceVarianceUseCase,
)
from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema
from frontend.desktop.modules.purchasing.enterprise_presenter import (
    EnterprisePurchasingPresenter,
)


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
        },
        session_context=session_context,
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
