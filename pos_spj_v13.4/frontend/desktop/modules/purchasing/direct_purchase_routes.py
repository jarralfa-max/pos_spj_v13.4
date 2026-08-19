"""Composition root for the direct-purchase UI.

The only place that touches the connection to wire the read services and use
cases. The view/pages never see the connection nor the AppContainer.
"""

from __future__ import annotations

from backend.application.procurement.adapters.product_catalog_adapter import (
    ProcurementProductCatalogAdapter,
)
from backend.application.procurement.adapters.supplier_profile_adapter import (
    InventoryReceiptStatusAdapter,
    SupplierFinanceAdapter,
    SupplierProfileAdapter,
)
from backend.application.procurement.queries import (
    DirectPurchaseReadService,
    SupplierPickerQueryService,
)
from backend.application.procurement.queries.purchase_template_read_service import (
    ProductPurchaseCostReadService,
    PurchaseTemplateReadService,
)
from backend.application.procurement.queries.supplier_directory_query_service import (
    SupplierDirectoryQueryService,
)
from backend.application.procurement.authorization import PurchaseAuthorizationPolicy
from backend.application.procurement.session_authorization import (
    ProcurementSessionPermissionChecker,
)
from backend.application.procurement.use_cases.direct_purchase_use_cases import (
    AuthorizeDirectPurchaseUseCase,
    ConfirmDirectPurchaseUseCase,
    CreateDirectPurchaseUseCase,
    ReverseDirectPurchaseUseCase,
)
from backend.application.procurement.use_cases.pricing_use_cases import (
    RecordPurchasePriceVarianceUseCase,
)
from backend.domain.procurement.pricing_policies import PriceVariancePolicy
from frontend.desktop.modules.purchasing.direct_purchase_presenter import (
    DirectPurchasePresenter,
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


def build_direct_purchase_presenter(connection, session_context=None) -> DirectPurchasePresenter:
    authorization = PurchaseAuthorizationPolicy(
        ProcurementSessionPermissionChecker(session_context))
    supplier_directory = SupplierDirectoryQueryService(connection)
    return DirectPurchasePresenter(
        connection_provider=lambda: connection,
        read_service=DirectPurchaseReadService(connection),
        supplier_picker=SupplierPickerQueryService(connection),
        product_catalog=ProcurementProductCatalogAdapter(connection),
        use_cases={
            "create": CreateDirectPurchaseUseCase(authorization, supplier_directory),
            "authorize": AuthorizeDirectPurchaseUseCase(authorization),
            "confirm": ConfirmDirectPurchaseUseCase(authorization),
            "reverse": ReverseDirectPurchaseUseCase(authorization),
            "record_variance": RecordPurchasePriceVarianceUseCase(authorization),
        },
        session_context=session_context,
        templates=PurchaseTemplateReadService(connection),
        costs=ProductPurchaseCostReadService(connection),
        variance_policy=PriceVariancePolicy(),
        event_dispatcher=_post_commit_dispatcher(connection),
        supplier_profile=SupplierProfileAdapter(connection),
        supplier_finance=SupplierFinanceAdapter(connection),
        receipt_status=InventoryReceiptStatusAdapter(connection),
    )
