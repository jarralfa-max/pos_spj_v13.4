"""Composition root for the suppliers UI.

The only place that touches the connection to wire supplier query services and
use cases. The view and pages never see the connection nor the AppContainer.
"""

from __future__ import annotations

from backend.application.suppliers.queries import (
    SearchSuppliersQueryService,
    SupplierDashboardQueryService,
    SupplierDetailQueryService,
    SupplierFinancialSummaryQueryService,
    SupplierPerformanceQueryService,
    SupplierRiskQueryService,
)
from backend.application.suppliers.use_cases.detail_use_cases import (
    AddSupplierBankAccountUseCase,
    AddSupplierContactUseCase,
    AssignProductToSupplierUseCase,
    UpdateSupplierCommercialTermsUseCase,
    UploadSupplierDocumentUseCase,
    VerifySupplierBankAccountUseCase,
)
from backend.application.suppliers.use_cases.evaluate_supplier_use_case import (
    EvaluateSupplierUseCase,
)
from backend.application.suppliers.use_cases.lifecycle_use_cases import (
    ActivateSupplierUseCase,
    ApproveSupplierUseCase,
    BlockSupplierUseCase,
    CreateSupplierUseCase,
    RejectSupplierUseCase,
    SubmitSupplierForApprovalUseCase,
    SuspendSupplierUseCase,
    UnblockSupplierUseCase,
    UpdateSupplierUseCase,
)
from backend.infrastructure.db.schema.supplier_schema import create_supplier_schema
from frontend.desktop.modules.finance.suppliers.supplier_presenter import SupplierPresenter


def build_supplier_presenter(connection, session_context=None) -> SupplierPresenter:
    # Idempotent bootstrap so the schema exists even on a dev DB opened before
    # migration 119 ran.
    create_supplier_schema(connection)

    query_services = {
        "dashboard": SupplierDashboardQueryService(connection),
        "search": SearchSuppliersQueryService(connection),
        "detail": SupplierDetailQueryService(connection),
        "financial": SupplierFinancialSummaryQueryService(connection),
        "performance": SupplierPerformanceQueryService(connection),
        "risk": SupplierRiskQueryService(connection),
    }
    use_cases = {
        "create": CreateSupplierUseCase(),
        "update": UpdateSupplierUseCase(),
        "submit": SubmitSupplierForApprovalUseCase(),
        "approve": ApproveSupplierUseCase(),
        "reject": RejectSupplierUseCase(),
        "activate": ActivateSupplierUseCase(),
        "suspend": SuspendSupplierUseCase(),
        "block": BlockSupplierUseCase(),
        "unblock": UnblockSupplierUseCase(),
        "add_contact": AddSupplierContactUseCase(),
        "add_bank": AddSupplierBankAccountUseCase(),
        "verify_bank": VerifySupplierBankAccountUseCase(),
        "update_terms": UpdateSupplierCommercialTermsUseCase(),
        "assign_product": AssignProductToSupplierUseCase(),
        "upload_document": UploadSupplierDocumentUseCase(),
        "evaluate": EvaluateSupplierUseCase(),
    }
    return SupplierPresenter(
        connection_provider=lambda: connection,
        query_services=query_services,
        use_cases=use_cases,
        session_context=session_context,
    )


def create_suppliers_view(container, parent=None):
    """Factory: build the SuppliersView from an app container / connection."""
    from frontend.desktop.modules.finance.suppliers.suppliers_view import SuppliersView

    connection = getattr(container, "db", None) or getattr(container, "db_conn", None) \
        or container
    session_context = getattr(container, "session_context", None)
    presenter = build_supplier_presenter(connection, session_context)
    return SuppliersView(presenter, parent)
