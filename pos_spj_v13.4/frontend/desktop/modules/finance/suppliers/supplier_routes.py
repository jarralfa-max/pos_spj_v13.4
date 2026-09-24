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
from backend.application.suppliers.authorization import SupplierAuthorizationPolicy
from backend.application.suppliers.session_authorization import (
    SupplierSessionPermissionChecker,
)
from backend.application.suppliers.use_cases.detail_use_cases import (
    AddSupplierAddressUseCase,
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
    DeactivateSupplierUseCase,
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
    # RBAC real. Antes CADA caso de uso se construía sin checker, y
    # `SupplierAuthorizationPolicy` sin checker PERMITE todo: cualquier usuario
    # con acceso al módulo podía aprobar, bloquear o verificar cuentas
    # bancarias. El checker traduce los códigos planos al vocabulario grueso
    # que la base sí concede (ver su docstring) y deniega lo no mapeado.
    authorization = SupplierAuthorizationPolicy(
        SupplierSessionPermissionChecker(session_context))

    use_cases = {
        "create": CreateSupplierUseCase(authorization),
        "update": UpdateSupplierUseCase(authorization),
        "submit": SubmitSupplierForApprovalUseCase(authorization),
        "approve": ApproveSupplierUseCase(authorization),
        "reject": RejectSupplierUseCase(authorization),
        "activate": ActivateSupplierUseCase(authorization),
        "suspend": SuspendSupplierUseCase(authorization),
        # Baja y reactivación: la transición a INACTIVO existía en el dominio
        # pero no tenía caso de uso, así que no era alcanzable desde ninguna
        # pantalla. Reactivar usa `activate`, que ahora admite INACTIVE.
        "deactivate": DeactivateSupplierUseCase(authorization),
        "block": BlockSupplierUseCase(authorization),
        "unblock": UnblockSupplierUseCase(authorization),
        "add_contact": AddSupplierContactUseCase(authorization),
        # `AddSupplierAddressUseCase` estaba construido y probado desde el
        # inicio, pero nunca se cableó: la dirección del proveedor —uno de los
        # grupos de datos del ciclo comercial— no era capturable.
        "add_address": AddSupplierAddressUseCase(authorization),
        "add_bank": AddSupplierBankAccountUseCase(authorization),
        "verify_bank": VerifySupplierBankAccountUseCase(authorization),
        "update_terms": UpdateSupplierCommercialTermsUseCase(authorization),
        "assign_product": AssignProductToSupplierUseCase(authorization),
        "upload_document": UploadSupplierDocumentUseCase(authorization),
        "evaluate": EvaluateSupplierUseCase(authorization),
    }
    return SupplierPresenter(
        connection_provider=lambda: connection,
        query_services=query_services,
        use_cases=use_cases,
        session_context=session_context,
    )


# `create_suppliers_view(container, ...)` used to live here and resolved its own
# dependencies out of whatever object it was handed
# (`getattr(container, "db", None) or getattr(container, "db_conn", None) or container`)
# — the Service-Locator-at-the-frontier pattern the architecture rules forbid, and
# the reason this file tripped the finance bounded-context guard while its own
# docstring claimed the opposite. It had zero callers: the real consumer,
# `frontend/desktop/modules/finance/pages/suppliers_page.py`, already goes through
# `build_supplier_presenter(connection, session_context)` with both dependencies
# passed explicitly. Deleted rather than rewritten, since nothing needed it.
