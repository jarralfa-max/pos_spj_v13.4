"""Composition root for the direct-purchase UI.

The only place that touches the connection to wire the read services and use
cases. The view/pages never see the connection nor the AppContainer.
"""

from __future__ import annotations

from backend.application.procurement.queries import (
    DirectPurchaseReadService,
    SupplierPickerQueryService,
)
from backend.application.procurement.queries.purchase_template_read_service import (
    ProductPurchaseCostReadService,
    PurchaseTemplateReadService,
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
from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema
from frontend.desktop.modules.purchasing.direct_purchase_presenter import (
    DirectPurchasePresenter,
)


def build_direct_purchase_presenter(connection, session_context=None) -> DirectPurchasePresenter:
    # Idempotent bootstrap so the schema exists even on a dev DB opened before
    # migration 120 ran.
    create_procurement_schema(connection)
    return DirectPurchasePresenter(
        connection_provider=lambda: connection,
        read_service=DirectPurchaseReadService(connection),
        supplier_picker=SupplierPickerQueryService(connection),
        use_cases={
            "create": CreateDirectPurchaseUseCase(),
            "authorize": AuthorizeDirectPurchaseUseCase(),
            "confirm": ConfirmDirectPurchaseUseCase(),
            "reverse": ReverseDirectPurchaseUseCase(),
            "record_variance": RecordPurchasePriceVarianceUseCase(),
        },
        session_context=session_context,
        templates=PurchaseTemplateReadService(connection),
        costs=ProductPurchaseCostReadService(connection),
        variance_policy=PriceVariancePolicy(),
    )


def create_direct_purchase_view(container, parent=None):
    """Factory: build the DirectPurchaseView from an app container / connection."""
    from frontend.desktop.modules.purchasing.direct_purchase_view import (
        DirectPurchaseView,
    )

    connection = getattr(container, "db", None) or getattr(container, "db_conn", None) \
        or container
    session_context = getattr(container, "session_context", None)
    presenter = build_direct_purchase_presenter(connection, session_context)
    return DirectPurchaseView(presenter, parent)
