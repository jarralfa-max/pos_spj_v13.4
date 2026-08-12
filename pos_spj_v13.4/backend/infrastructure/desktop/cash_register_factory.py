"""Desktop composition root for the canonical Caja module.

This is the only layer allowed to know about the application container. The
frontend receives an explicit presenter with query services, use cases, session
and active-context callbacks already wired.
"""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.blind_count_query_service import BlindCountQueryService
from backend.application.cash_register.configuration_query_service import CashConfigurationQueryService
from backend.application.cash_register.device_query_service import CashDeviceQueryService
from backend.application.cash_register.device_use_cases import (
    AssignCashDeviceUseCase,
    CreateCashDeviceUseCase,
    SetCashDeviceStatusUseCase,
)
from backend.application.cash_register.ledger_query_service import CashLedgerQueryService
from backend.application.cash_register.ledger_use_cases import (
    RegisterCashMovementUseCase,
    ReverseCashMovementUseCase,
)
from backend.application.cash_register.session_authorization import (
    CashSessionBranchScopeChecker,
    CashSessionPermissionChecker,
)
from backend.application.cash_register.shift_use_cases import (
    BeginCashShiftClosingUseCase,
    OpenCashShiftUseCase,
    ResumeCashShiftUseCase,
    SuspendCashShiftUseCase,
)
from backend.domain.cash_register.policies.security_policies import CashMonetaryLimitPolicy
from backend.infrastructure.db.repositories.cash_register.configuration_repository import (
    CashConfigurationReadRepository,
)
from backend.infrastructure.db.repositories.cash_register.repositories import (
    CashDeviceRepository,
    CashLedgerRepository,
)
from frontend.desktop.modules.cash_register import CashRegisterPresenter, CashRegisterWorkspace


class _AnonymousSession:
    is_active = False
    user_id = ""
    active_branch_id = ""

    @staticmethod
    def tiene_permiso(_permission: str) -> bool:
        return False


def _connection(composition_root):
    return getattr(composition_root, "db", composition_root)


def _session(composition_root):
    return getattr(composition_root, "session", _AnonymousSession())


def _cash_limit_policy(connection, operation_type: str) -> CashMonetaryLimitPolicy:
    row = connection.execute(
        """SELECT approval_threshold,hard_cap
        FROM cash_operation_limits
        WHERE operation_type=? AND active=1
        ORDER BY effective_from DESC LIMIT 1""",
        (operation_type,),
    ).fetchone()
    threshold = Decimal(str(row[0])) if row else Decimal("0")
    hard_cap = Decimal(str(row[1])) if row else Decimal("0")
    return CashMonetaryLimitPolicy(approval_threshold=threshold, hard_cap=hard_cap)


def build_cash_register_presenter(composition_root) -> CashRegisterPresenter:
    connection = _connection(composition_root)
    session = _session(composition_root)
    authorization = getattr(composition_root, "cash_authorization_policy", None)
    if authorization is None:
        authorization = CashAuthorizationPolicy(
            permissions=CashSessionPermissionChecker(session),
            scopes=CashSessionBranchScopeChecker(session),
        )

    def resolve_attr(name: str, factory):
        value = getattr(composition_root, name, None)
        return value if value is not None else factory()

    query_services = {
        "configuration": resolve_attr(
            "cash_configuration_query_service",
            lambda: CashConfigurationQueryService(CashConfigurationReadRepository(connection)),
        ),
        "hardware": resolve_attr(
            "cash_devices_query_service",
            lambda: CashDeviceQueryService(CashDeviceRepository(connection)),
        ),
        "ledger": resolve_attr(
            "cash_ledger_query_service",
            lambda: CashLedgerQueryService(CashLedgerRepository(connection)),
        ),
        "blind_count": resolve_attr(
            "cash_blind_count_query_service",
            lambda: BlindCountQueryService(connection, authorization),
        ),
    }
    use_cases = {
        "cash_device_create_uc": resolve_attr(
            "cash_device_create_uc", lambda: CreateCashDeviceUseCase(authorization)
        ),
        "cash_device_status_uc": resolve_attr(
            "cash_device_status_uc", lambda: SetCashDeviceStatusUseCase(authorization)
        ),
        "cash_device_assign_uc": resolve_attr(
            "cash_device_assign_uc", lambda: AssignCashDeviceUseCase(authorization)
        ),
        "cash_open_shift_uc": resolve_attr(
            "cash_open_shift_uc",
            lambda: OpenCashShiftUseCase(
                authorization, _cash_limit_policy(connection, "OPENING_FLOAT")
            ),
        ),
        "cash_suspend_shift_uc": resolve_attr(
            "cash_suspend_shift_uc", lambda: SuspendCashShiftUseCase(authorization)
        ),
        "cash_resume_shift_uc": resolve_attr(
            "cash_resume_shift_uc", lambda: ResumeCashShiftUseCase(authorization)
        ),
        "cash_begin_shift_closing_uc": resolve_attr(
            "cash_begin_shift_closing_uc", lambda: BeginCashShiftClosingUseCase(authorization)
        ),
        "cash_register_movement_uc": resolve_attr(
            "cash_register_movement_uc",
            lambda: RegisterCashMovementUseCase(
                authorization, _cash_limit_policy(connection, "MANUAL_MOVEMENT")
            ),
        ),
        "cash_reverse_movement_uc": resolve_attr(
            "cash_reverse_movement_uc", lambda: ReverseCashMovementUseCase(authorization)
        ),
    }

    def active_shift_id() -> str | None:
        value = getattr(composition_root, "active_cash_shift_id", None)
        return str(value) if value else None

    def active_count_context() -> tuple[str, str, str] | None:
        count_id = getattr(composition_root, "active_cash_count_id", None)
        branch_id = str(
            getattr(session, "active_branch_id", None)
            or getattr(session, "branch_id", None)
            or getattr(composition_root, "sucursal_id", "")
            or ""
        )
        user_id = str(getattr(session, "user_id", "") or "")
        if count_id and branch_id and user_id:
            return str(count_id), branch_id, user_id
        return None

    return CashRegisterPresenter(
        session_context=session,
        query_services=query_services,
        use_cases=use_cases,
        active_shift_provider=active_shift_id,
        active_count_context_provider=active_count_context,
    )


def create_cash_register_view(composition_root, parent=None) -> CashRegisterWorkspace:
    return CashRegisterWorkspace(
        presenter=build_cash_register_presenter(composition_root),
        parent=parent,
    )


class CashRegisterModuleHost(QWidget):
    def __init__(self, composition_root, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("cashRegisterModuleHost")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.presenter = build_cash_register_presenter(composition_root)
        self.view = CashRegisterWorkspace(presenter=self.presenter, parent=self)
        layout.addWidget(self.view)

    def refresh_permissions(self) -> None:
        self.view.refresh_permissions()
