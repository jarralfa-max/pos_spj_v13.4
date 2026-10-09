"""Desktop composition root for the canonical Caja module.

This is the only layer allowed to know about the application container. The
frontend receives an explicit presenter with query services, use cases, session
and active-context callbacks already wired.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.blind_count_query_service import BlindCountQueryService
from backend.application.cash_register.blind_count_use_cases import (
    CaptureBlindCountDenominationUseCase,
    ConfirmBlindCountUseCase,
    StartBlindCountUseCase,
)
from backend.application.cash_register.configuration_query_service import CashConfigurationQueryService
from backend.application.cash_register.configuration_use_cases import (
    ConfigureCashRegisterUseCase,
    DeactivateCashConfigurationUseCase,
    ManageCashAlertRecipientUseCase,
    build_cash_catalog_command,
)
from backend.application.cash_register.device_query_service import CashDeviceQueryService
from backend.application.cash_register.device_use_cases import (
    AssignCashDeviceUseCase,
    CreateCashDeviceUseCase,
    DiagnoseCashHardwareUseCase,
    SetCashDeviceStatusUseCase,
)
from backend.application.cash_register.hardware_use_cases import OpenCashDrawerUseCase
from backend.application.cash_register.denomination_query_service import CashDenominationQueryService
from backend.application.cash_register.difference_query_service import CashDifferenceQueryService
from backend.application.cash_register.difference_use_cases import (
    ExplainCashDifferenceUseCase,
    ResolveCashDifferenceUseCase,
    ReviewCashDifferenceUseCase,
)
from backend.application.cash_register.ledger_query_service import CashLedgerQueryService
from backend.application.cash_register.handover_query_service import CashHandoverQueryService
from backend.application.cash_register.ledger_use_cases import (
    RegisterCashMovementUseCase,
    ReverseCashMovementUseCase,
)
from backend.application.cash_register.movement_reason_query_service import (
    CashMovementReasonQueryService,
)
from backend.application.cash_register.movement_use_cases import (
    DeliverTreasuryHandoverUseCase,
    DisputeTreasuryHandoverUseCase,
    PrepareTreasuryHandoverUseCase,
    ReceiveTreasuryHandoverUseCase,
    RegisterSafeDropUseCase,
)
from backend.application.cash_register.notifications import (
    CashInAppAlertQueryService,
    DispatchCashNotificationsUseCase,
    PrepareCashNotificationsUseCase,
)
from backend.application.cash_register.offline_sync import (
    CashOfflineSyncService,
    CashSyncStateQueryService,
    ResolveCashSyncConflictUseCase,
    SetCashSyncConnectivityUseCase,
)
from backend.application.cash_register.operational_read_query_service import (
    CashOperationalReadQueryService,
)
from backend.application.cash_register.overview_query_service import CashOverviewQueryService
from backend.application.cash_register.permissions import CashPermissions
from backend.application.cash_register.printing import (
    CashPrintDocument,
    CashPrintDocumentType,
    CashPrintFormat,
    DispatchCashPrintQueueUseCase,
    PrintCashDocumentCommand,
    PrintCashDocumentUseCase,
)
from backend.application.cash_register.refund_integration import CashRefundIntegrationService
from backend.application.cash_register.session_authorization import (
    CashSessionBranchScopeChecker,
    CashSessionPermissionChecker,
)
from backend.application.cash_register.shift_query_service import CashShiftQueryService
from backend.application.security.authorizer_permission_checker import AuthorizerPermissionChecker
from backend.application.security.session_or_authorizer_checker import (
    SessionOrAuthorizerBranchScopeChecker,
    SessionOrAuthorizerPermissionChecker,
)
from backend.domain.cash_register.exceptions import (
    CashAuthorizationRequiredError,
    CashConfigurationError,
    CashInvalidStateError,
)
from backend.domain.document_output.enums import DocumentType
from backend.infrastructure.hardware.cash_drawer_gateway import PrinterKickCashDrawerGateway
from backend.infrastructure.hardware.cash_document_printer import (
    CashDocumentPrinter,
    resolve_cash_printer,
)
from backend.infrastructure.printing.routed_printer import PrintTargetUnavailable
from backend.security.authentication.errors import AuthenticationFailedError
from backend.security.authentication.verify_authorizer_credentials_use_case import (
    build_authorizer_credentials_verifier,
)
from backend.application.cash_register.shift_use_cases import (
    BeginCashShiftClosingUseCase,
    OpenCashShiftUseCase,
    ResumeCashShiftUseCase,
    SuspendCashShiftUseCase,
)
from backend.application.cash_register.x_cut_query_service import XCutQueryService
from backend.application.cash_register.x_cut_use_cases import GenerateXCutUseCase
from backend.application.cash_register.z_cut_query_service import CashZCutQueryService
from backend.application.cash_register.z_cut_use_cases import (
    GenerateZCutUseCase,
    NotifyZCutUseCase,
)
from backend.domain.cash_register.enums import CashMovementType
from backend.shared.ids import new_uuid
from backend.infrastructure.desktop.cash_operational_context import (
    DesktopCashOperationalContextResolver,
)
from backend.infrastructure.db.repositories.cash_register.operation_limits import (
    EffectiveCashLimitPolicy,
)
from backend.infrastructure.db.repositories.cash_register.printing_repository import CashPrintRepository
from backend.infrastructure.db.repositories.cash_register.configuration_repository import (
    CashConfigurationReadRepository,
)
from backend.infrastructure.db.repositories.cash_register.repositories import (
    CashCountRepository,
    CashDeviceRepository,
    CashHandoverRepository,
    CashLedgerRepository,
    CashMovementReasonRepository,
)
from backend.infrastructure.integrations.cash_notification_senders import (
    EmailNotificationSender,
    ErpWhatsAppTextClient,
    WhatsAppNotificationSender,
)
from backend.infrastructure.printing.cash_register_renderers import CashDocumentEscPosRenderer
from frontend.desktop.modules.cash_register import CashRegisterPresenter, CashRegisterWorkspace


class _AnonymousSession:
    is_active = False
    user_id = ""
    active_branch_id = ""

    @staticmethod
    def tiene_permiso(_permission: str) -> bool:
        return False


class _NoOpZCutNotifier:
    def notify(self, document: dict[str, object]) -> None:
        return None


class _MissingCashSyncTransport:
    def push(self, *, device_id: str, branch_id: str, envelopes):
        raise RuntimeError("Gateway de sincronizacion de Caja no configurado")


class _DesktopCashSyncQueryService:
    def __init__(self, connection, query: CashSyncStateQueryService) -> None:
        self._connection = connection
        self._query = query

    def get(self, *, device_id: str, branch_id: str, actor_user_id: str) -> dict:
        _ensure_cash_sync_device(self._connection, device_id=device_id, branch_id=branch_id)
        return self._query.get(
            self._connection,
            device_id=device_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
        )

    def list_envelopes(self, *, device_id: str, branch_id: str,
                       actor_user_id: str, limit: int = 100) -> list[dict]:
        _ensure_cash_sync_device(self._connection, device_id=device_id, branch_id=branch_id)
        return self._query.list_envelopes(
            self._connection,
            device_id=device_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            limit=limit,
        )

    def list_conflicts(self, *, device_id: str, branch_id: str,
                       actor_user_id: str) -> list[dict]:
        _ensure_cash_sync_device(self._connection, device_id=device_id, branch_id=branch_id)
        return self._query.list_conflicts(
            self._connection,
            device_id=device_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
        )


class _DesktopCashNotificationQueryService:
    def __init__(self, connection, query: CashInAppAlertQueryService) -> None:
        self._connection = connection
        self._query = query

    def dashboard(self, *, user_id: str, branch_id: str) -> dict[str, int]:
        return self._query.dashboard(self._connection, user_id=user_id, branch_id=branch_id)

    def unread(self, *, user_id: str, branch_id: str) -> list[dict]:
        return self._query.unread(self._connection, user_id=user_id, branch_id=branch_id)

    def recent_jobs(self, *, user_id: str, branch_id: str,
                    limit: int = 100) -> list[dict]:
        return self._query.recent_jobs(
            self._connection, user_id=user_id, branch_id=branch_id, limit=limit
        )


def _connection(composition_root):
    return getattr(composition_root, "db", composition_root)


def _session(composition_root):
    return getattr(composition_root, "session", _AnonymousSession())


def _cash_limit_policy(connection, operation_type: str) -> EffectiveCashLimitPolicy:
    return EffectiveCashLimitPolicy(connection, operation_type)


def _ensure_cash_sync_device(connection, *, device_id: str | None,
                             branch_id: str | None) -> str | None:
    """Register the active POS terminal as sync identity if session lacks one."""
    if not device_id or not branch_id:
        return None
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    connection.execute(
        """INSERT INTO cash_sync_devices
        (id,branch_id,local_sequence,last_synced_sequence,connectivity,sync_status,updated_at)
        VALUES(?,?,0,0,'ONLINE','IDLE',?)
        ON CONFLICT(id) DO NOTHING""",
        (str(device_id), str(branch_id), now),
    )
    connection.commit()
    return str(device_id)


def _after_cash_command(connection, handler, deliver_notifications):
    """Tras una operación de Caja ya confirmada (CASH-26 bloque 2):

    1. entrega a Finanzas lo pendiente del `cash_outbox`;
    2. envía los avisos listos (en el sistema y WhatsApp). Antes sólo salían
       si alguien pulsaba «Enviar» en la página de Notificaciones.

    Un fallo aquí no deshace la operación: el evento o el aviso quedan
    pendientes con su error y salen en el siguiente intento.
    """
    def run(*args, **kwargs):
        result = handler(*args, **kwargs)
        log = logging.getLogger("spj.cash_register.factory")
        try:
            from backend.application.cash_register.finance_wiring import dispatch_cash_outbox
            from backend.shared.events.application_bus import get_bus
            dispatch_cash_outbox(connection, get_bus())
        except Exception:  # noqa: BLE001 - nunca propaga a la pantalla
            log.exception("despacho de cash_outbox fallido")
        try:
            deliver_notifications()
        except Exception:  # noqa: BLE001 - nunca propaga a la pantalla
            log.exception("envío de avisos de Caja fallido")
        return result
    return run


def build_cash_register_presenter(composition_root) -> CashRegisterPresenter:
    connection = _connection(composition_root)
    session = _session(composition_root)
    authorization = getattr(composition_root, "cash_authorization_policy", None)
    if authorization is None:
        # Quien opera se valida contra su sesión; el AUTORIZADOR de una excepción
        # (otro usuario, ya probado con su clave) contra `rol_permisos`. Con sólo
        # el verificador de sesión, toda autorización en caliente se denegaba.
        authorization = CashAuthorizationPolicy(
            permissions=SessionOrAuthorizerPermissionChecker(
                session=session,
                session_checker=CashSessionPermissionChecker(session),
                authorizer_checker=AuthorizerPermissionChecker(
                    connection, branch_id=getattr(session, "active_branch_id", None) or None),
            ),
            scopes=SessionOrAuthorizerBranchScopeChecker(
                session=session, session_scopes=CashSessionBranchScopeChecker(session)),
        )

    def resolve_attr(name: str, factory):
        value = getattr(composition_root, name, None)
        return value if value is not None else factory()

    query_services = {
        "overview": resolve_attr(
            "cash_overview_query_service",
            lambda: CashOverviewQueryService(connection, authorization),
        ),
        "shifts": resolve_attr(
            "cash_shift_query_service",
            lambda: CashShiftQueryService(connection, authorization),
        ),
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
        "movement_reasons": resolve_attr(
            "cash_movement_reason_query_service",
            lambda: CashMovementReasonQueryService(CashMovementReasonRepository(connection)),
        ),
        "denominations": resolve_attr(
            "cash_denomination_query_service",
            lambda: CashDenominationQueryService(CashCountRepository(connection)),
        ),
        "handover": resolve_attr(
            "cash_handover_query_service",
            lambda: CashHandoverQueryService(CashHandoverRepository(connection)),
        ),
        "differences": resolve_attr(
            "cash_difference_query_service",
            lambda: CashDifferenceQueryService(connection, authorization),
        ),
        "x_cut": resolve_attr(
            "cash_x_cut_query_service",
            lambda: XCutQueryService(connection, authorization),
        ),
        "z_cut": resolve_attr(
            "cash_z_cut_query_service",
            lambda: CashZCutQueryService(connection, authorization),
        ),
        "sync": resolve_attr(
            "cash_sync_query_service",
            lambda: _DesktopCashSyncQueryService(
                connection, CashSyncStateQueryService(authorization)
            ),
        ),
        "notifications": resolve_attr(
            "cash_notifications_query_service",
            lambda: _DesktopCashNotificationQueryService(
                connection, CashInAppAlertQueryService(authorization)
            ),
        ),
        "operational_read": resolve_attr(
            "cash_operational_read_query_service",
            lambda: CashOperationalReadQueryService(connection, authorization),
        ),
    }
    print_repository = resolve_attr(
        "cash_print_repository", lambda: CashPrintRepository(connection)
    )
    print_gateway = resolve_attr(
        "cash_print_gateway", lambda: CashDocumentPrinter(connection)
    )
    hardware_gateway = resolve_attr(
        "cash_hardware_gateway",
        lambda: PrinterKickCashDrawerGateway(
            connection,
            workstation_id=str(getattr(session, "workstation_id", "") or "") or None),
    )
    whatsapp_client = (
        getattr(composition_root, "cash_whatsapp_client", None)
        or getattr(composition_root, "whatsapp_message_service", None)
        or ErpWhatsAppTextClient(connection)
    )
    email_client = (
        getattr(composition_root, "cash_email_client", None)
        or getattr(composition_root, "email_service", None)
    )
    whatsapp_sender = WhatsAppNotificationSender(whatsapp_client) if whatsapp_client is not None else None
    email_sender = EmailNotificationSender(email_client) if email_client is not None else None
    safe_drop_limit = _cash_limit_policy(connection, "SAFE_DROP")
    use_cases = {
        "cash_device_create_uc": resolve_attr(
            "cash_device_create_uc", lambda: CreateCashDeviceUseCase(authorization)
        ),
        "cash_configure_uc": resolve_attr(
            "cash_configure_uc", lambda: ConfigureCashRegisterUseCase(authorization)
        ),
        "cash_device_status_uc": resolve_attr(
            "cash_device_status_uc", lambda: SetCashDeviceStatusUseCase(authorization)
        ),
        "cash_device_assign_uc": resolve_attr(
            "cash_device_assign_uc", lambda: AssignCashDeviceUseCase(authorization)
        ),
        "cash_hardware_diagnose_uc": resolve_attr(
            "cash_hardware_diagnose_uc",
            lambda: DiagnoseCashHardwareUseCase(authorization, hardware_gateway),
        ),
        "cash_open_drawer_hardware_uc": resolve_attr(
            "cash_open_drawer_hardware_uc",
            lambda: OpenCashDrawerUseCase(authorization, hardware_gateway),
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
        "cash_start_blind_count_uc": resolve_attr(
            "cash_start_blind_count_uc", lambda: StartBlindCountUseCase(authorization)
        ),
        "cash_capture_blind_count_uc": resolve_attr(
            "cash_capture_blind_count_uc",
            lambda: CaptureBlindCountDenominationUseCase(authorization),
        ),
        "cash_confirm_blind_count_uc": resolve_attr(
            "cash_confirm_blind_count_uc", lambda: ConfirmBlindCountUseCase(authorization)
        ),
        "cash_register_movement_uc": resolve_attr(
            "cash_register_movement_uc",
            lambda: RegisterCashMovementUseCase(
                authorization, _cash_limit_policy(connection, "MANUAL_MOVEMENT")
            ),
        ),
        "cash_safe_drop_uc": resolve_attr(
            "cash_safe_drop_uc",
            lambda: RegisterSafeDropUseCase(authorization, safe_drop_limit),
        ),
        "cash_prepare_handover_uc": resolve_attr(
            "cash_prepare_handover_uc", lambda: PrepareTreasuryHandoverUseCase(authorization)
        ),
        "cash_deliver_handover_uc": resolve_attr(
            "cash_deliver_handover_uc", lambda: DeliverTreasuryHandoverUseCase(authorization)
        ),
        "cash_receive_handover_uc": resolve_attr(
            "cash_receive_handover_uc", lambda: ReceiveTreasuryHandoverUseCase(authorization)
        ),
        "cash_dispute_handover_uc": resolve_attr(
            "cash_dispute_handover_uc", lambda: DisputeTreasuryHandoverUseCase(authorization)
        ),
        "cash_refund_integration_service": resolve_attr(
            "cash_refund_integration_service",
            lambda: CashRefundIntegrationService(
                authorization, _cash_limit_policy(connection, "REFUND")
            ),
        ),
        "cash_explain_difference_uc": resolve_attr(
            "cash_explain_difference_uc", lambda: ExplainCashDifferenceUseCase(authorization)
        ),
        "cash_review_difference_uc": resolve_attr(
            "cash_review_difference_uc", lambda: ReviewCashDifferenceUseCase(authorization)
        ),
        "cash_resolve_difference_uc": resolve_attr(
            "cash_resolve_difference_uc", lambda: ResolveCashDifferenceUseCase(authorization)
        ),
        "cash_generate_x_cut_uc": resolve_attr(
            "cash_generate_x_cut_uc", lambda: GenerateXCutUseCase(authorization)
        ),
        "cash_generate_z_cut_uc": resolve_attr(
            "cash_generate_z_cut_uc", lambda: GenerateZCutUseCase(authorization)
        ),
        "cash_notify_z_cut_uc": resolve_attr(
            "cash_notify_z_cut_uc",
            lambda: NotifyZCutUseCase(
                authorization,
                getattr(composition_root, "cash_z_cut_notification_gateway", _NoOpZCutNotifier()),
            ),
        ),
        "cash_prepare_notifications_uc": resolve_attr(
            "cash_prepare_notifications_uc", lambda: PrepareCashNotificationsUseCase()
        ),
        "cash_dispatch_notifications_uc": resolve_attr(
            "cash_dispatch_notifications_uc",
            lambda: DispatchCashNotificationsUseCase(
                whatsapp=whatsapp_sender,
                email=email_sender,
            ),
        ),
        "cash_reverse_movement_uc": resolve_attr(
            "cash_reverse_movement_uc", lambda: ReverseCashMovementUseCase(authorization)
        ),
        "cash_sync_service": resolve_attr(
            "cash_sync_service",
            lambda: CashOfflineSyncService(
                getattr(composition_root, "cash_sync_transport", _MissingCashSyncTransport())
            ),
        ),
        "cash_sync_connectivity_uc": resolve_attr(
            "cash_sync_connectivity_uc", lambda: SetCashSyncConnectivityUseCase(authorization)
        ),
        "cash_sync_conflict_resolution_uc": resolve_attr(
            "cash_sync_conflict_resolution_uc", lambda: ResolveCashSyncConflictUseCase(authorization)
        ),
    }

    def prepare_notifications_for_operation(operation_id: str) -> None:
        cursor = connection.execute(
            "SELECT id FROM cash_domain_events WHERE operation_id=? ORDER BY occurred_at DESC,id DESC LIMIT 1",
            (operation_id,),
        )
        row = cursor.fetchone()
        if row is not None:
            use_cases["cash_prepare_notifications_uc"].execute(connection, event_id=str(row[0]))

    def prepare_notifications_for_entity(entity_id: str | None) -> None:
        """Eventos con su PROPIA operación dentro de otro caso de uso (la
        diferencia que detecta el Corte Z): antes sólo se preparaba el último
        evento de la operación del corte y la alerta de diferencia se perdía."""
        if not entity_id:
            return
        for row in connection.execute(
                "SELECT id FROM cash_domain_events WHERE entity_id=? ORDER BY occurred_at,id",
                (entity_id,)).fetchall():
            use_cases["cash_prepare_notifications_uc"].execute(connection, event_id=str(row[0]))

    def open_cash_shift_handler(
        *,
        branch_id: str,
        register_id: str,
        drawer_id: str,
        terminal_id: str,
        cashier_user_id: str,
        actor_user_id: str,
        opening_amount: Decimal,
    ):
        operation_id = new_uuid()
        result = use_cases["cash_open_shift_uc"].execute(
            connection,
            branch_id=branch_id,
            register_id=register_id,
            drawer_id=drawer_id,
            terminal_id=terminal_id,
            cashier_user_id=cashier_user_id,
            opening_amount=opening_amount,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
        )
        setattr(composition_root, "active_cash_shift_id", result.entity_id)
        prepare_notifications_for_operation(operation_id)
        return result

    def suspend_cash_shift_handler(
        *,
        shift_id: str,
        branch_id: str,
        actor_user_id: str,
        reason: str,
    ):
        operation_id = new_uuid()
        result = use_cases["cash_suspend_shift_uc"].execute(
            connection,
            shift_id=shift_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
            reason=reason,
        )
        prepare_notifications_for_operation(operation_id)
        return result

    def resume_cash_shift_handler(
        *,
        shift_id: str,
        branch_id: str,
        actor_user_id: str,
    ):
        operation_id = new_uuid()
        result = use_cases["cash_resume_shift_uc"].execute(
            connection,
            shift_id=shift_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
        )
        prepare_notifications_for_operation(operation_id)
        return result

    def begin_cash_shift_closing_handler(
        *,
        shift_id: str,
        branch_id: str,
        actor_user_id: str,
    ):
        operation_id = new_uuid()
        result = use_cases["cash_begin_shift_closing_uc"].execute(
            connection,
            shift_id=shift_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
        )
        prepare_notifications_for_operation(operation_id)
        return result

    def register_cash_movement_handler(
        *,
        shift_id: str,
        branch_id: str,
        actor_user_id: str,
        movement_type: str,
        amount: Decimal,
        concept: str,
        reason_code: str | None = None,
        authorized_by: str | None = None,
    ):
        if movement_type == CashMovementType.SAFE_DROP.value:
            if not reason_code:
                raise ValueError("El retiro a boveda requiere motivo configurado")
            operation_id = new_uuid()
            result = use_cases["cash_safe_drop_uc"].execute(
                connection,
                shift_id=shift_id,
                branch_id=branch_id,
                amount=amount,
                reason_code=reason_code,
                actor_user_id=actor_user_id,
                operation_id=operation_id,
                authorized_by=authorized_by,
            )
            if getattr(result, "alert_required", False):
                prepare_notifications_for_operation(operation_id)
            return result
        return use_cases["cash_register_movement_uc"].execute(
            connection,
            shift_id=shift_id,
            branch_id=branch_id,
            movement_type=CashMovementType(movement_type),
            amount=amount,
            concept=concept,
            actor_user_id=actor_user_id,
            operation_id=new_uuid(),
            authorized_by=authorized_by,
            reason_code=reason_code,
        )

    def start_blind_count_handler(
        *,
        shift_id: str,
        branch_id: str,
        counter_user_id: str,
    ):
        operation_id = new_uuid()
        result = use_cases["cash_start_blind_count_uc"].execute(
            connection,
            shift_id=shift_id,
            branch_id=branch_id,
            counter_user_id=counter_user_id,
            operation_id=operation_id,
        )
        setattr(composition_root, "active_cash_count_id", result.entity_id)
        prepare_notifications_for_operation(operation_id)
        return result

    def create_cash_device_handler(
        *,
        kind: str,
        branch_id: str,
        actor_user_id: str,
        name: str,
        register_id: str | None = None,
    ):
        operation_id = new_uuid()
        result = use_cases["cash_device_create_uc"].execute(
            connection,
            kind=kind,
            branch_id=branch_id,
            name=name,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
            register_id=register_id,
        )
        prepare_notifications_for_operation(operation_id)
        return result

    def configure_cash_catalog_handler(*, section: str, fields: dict, branch_id: str,
                                       actor_user_id: str):
        operation_id = new_uuid()
        result = use_cases["cash_configure_uc"].execute_typed(
            connection, command=build_cash_catalog_command(section, fields),
            actor_user_id=actor_user_id, branch_id=branch_id, operation_id=operation_id)
        prepare_notifications_for_operation(operation_id)
        return result

    def deactivate_cash_configuration_handler(*, section: str, row_id: str, branch_id: str,
                                              actor_user_id: str):
        return DeactivateCashConfigurationUseCase(authorization).execute(
            connection, section=section, row_id=row_id, actor_user_id=actor_user_id,
            branch_id=branch_id, operation_id=new_uuid())

    def add_cash_alert_recipient_handler(*, alert_rule_id: str, channel: str, address: str,
                                         display_name: str, branch_id: str,
                                         actor_user_id: str):
        return ManageCashAlertRecipientUseCase(authorization).add(
            connection, alert_rule_id=alert_rule_id, channel=channel, address=address,
            display_name=display_name, actor_user_id=actor_user_id, branch_id=branch_id,
            operation_id=new_uuid())

    def deactivate_cash_alert_recipient_handler(*, row_id: str, branch_id: str,
                                                actor_user_id: str):
        return ManageCashAlertRecipientUseCase(authorization).deactivate(
            connection, row_id=row_id, actor_user_id=actor_user_id, branch_id=branch_id,
            operation_id=new_uuid())

    def set_cash_device_status_handler(
        *,
        kind: str,
        device_id: str,
        branch_id: str,
        actor_user_id: str,
        activate: bool,
        reason: str = "",
        target_status: str | None = None,
    ):
        operation_id = new_uuid()
        result = use_cases["cash_device_status_uc"].execute(
            connection,
            kind=kind,
            device_id=device_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
            activate=activate,
            reason=reason,
            target_status=target_status,
        )
        prepare_notifications_for_operation(operation_id)
        return result

    def diagnose_cash_hardware_handler(
        *,
        device_id: str,
        branch_id: str,
        actor_user_id: str,
    ):
        operation_id = new_uuid()
        result = use_cases["cash_hardware_diagnose_uc"].execute(
            connection,
            device_id=device_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
        )
        prepare_notifications_for_operation(operation_id)
        return result

    def open_cash_drawer_hardware_handler(
        *,
        drawer_id: str,
        branch_id: str,
        actor_user_id: str,
        reason: str,
        sale_id: str | None = None,
    ):
        operation_id = new_uuid()
        result = use_cases["cash_open_drawer_hardware_uc"].execute(
            connection,
            drawer_id=drawer_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
            sale_id=sale_id,
            reason=reason,
        )
        prepare_notifications_for_operation(operation_id)
        return result

    def capture_blind_count_denomination_handler(
        *,
        count_id: str,
        branch_id: str,
        actor_user_id: str,
        denomination_id: str,
        quantity: int,
    ):
        operation_id = new_uuid()
        result = use_cases["cash_capture_blind_count_uc"].execute(
            connection,
            count_id=count_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            denomination_id=denomination_id,
            quantity=quantity,
            operation_id=operation_id,
        )
        return result

    def confirm_blind_count_handler(
        *,
        count_id: str,
        branch_id: str,
        actor_user_id: str,
    ):
        operation_id = new_uuid()
        result = use_cases["cash_confirm_blind_count_uc"].execute(
            connection,
            count_id=count_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
        )
        prepare_notifications_for_operation(operation_id)
        return result

    def reverse_cash_movement_handler(
        *,
        entry_id: str,
        branch_id: str,
        actor_user_id: str,
        authorized_by: str,
        reason: str,
    ):
        return use_cases["cash_reverse_movement_uc"].execute(
            connection,
            entry_id=entry_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            authorized_by=authorized_by,
            operation_id=new_uuid(),
            reason=reason,
        )

    def prepare_cash_handover_handler(
        *,
        safe_drop_entry_id: str,
        branch_id: str,
        actor_user_id: str,
        denominations: dict[str, int],
    ):
        operation_id = new_uuid()
        result = use_cases["cash_prepare_handover_uc"].execute(
            connection,
            safe_drop_entry_id=safe_drop_entry_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
            denominations=denominations,
        )
        prepare_notifications_for_operation(operation_id)
        return result

    def deliver_cash_handover_handler(
        *,
        handover_id: str,
        branch_id: str,
        actor_user_id: str,
        denominations: dict[str, int],
    ):
        operation_id = new_uuid()
        result = use_cases["cash_deliver_handover_uc"].execute(
            connection,
            handover_id=handover_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
            denominations=denominations,
        )
        prepare_notifications_for_operation(operation_id)
        return result

    def receive_cash_handover_handler(
        *,
        handover_id: str,
        branch_id: str,
        actor_user_id: str,
        denominations: dict[str, int],
    ):
        operation_id = new_uuid()
        result = use_cases["cash_receive_handover_uc"].execute(
            connection,
            handover_id=handover_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
            denominations=denominations,
        )
        prepare_notifications_for_operation(operation_id)
        return result

    def dispute_cash_handover_handler(
        *,
        handover_id: str,
        branch_id: str,
        actor_user_id: str,
        reason: str,
    ):
        operation_id = new_uuid()
        result = use_cases["cash_dispute_handover_uc"].execute(
            connection,
            handover_id=handover_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
            reason=reason,
        )
        prepare_notifications_for_operation(operation_id)
        return result

    def explain_cash_difference_handler(
        *,
        difference_id: str,
        branch_id: str,
        actor_user_id: str,
        explanation: str,
    ):
        operation_id = new_uuid()
        result = use_cases["cash_explain_difference_uc"].execute(
            connection,
            difference_id=difference_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
            explanation=explanation,
        )
        prepare_notifications_for_operation(operation_id)
        return result

    def review_cash_difference_handler(
        *,
        difference_id: str,
        branch_id: str,
        actor_user_id: str,
    ):
        operation_id = new_uuid()
        result = use_cases["cash_review_difference_uc"].execute(
            connection,
            difference_id=difference_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
        )
        prepare_notifications_for_operation(operation_id)
        return result

    def resolve_cash_difference_handler(
        *,
        difference_id: str,
        branch_id: str,
        actor_user_id: str,
        resolution: str,
    ):
        operation_id = new_uuid()
        result = use_cases["cash_resolve_difference_uc"].execute(
            connection,
            difference_id=difference_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
            resolution=resolution,
        )
        prepare_notifications_for_operation(operation_id)
        return result

    def generate_x_cut_handler(
        *,
        shift_id: str,
        branch_id: str,
        actor_user_id: str,
    ):
        operation_id = new_uuid()
        result = use_cases["cash_generate_x_cut_uc"].execute(
            connection,
            shift_id=shift_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
        )
        prepare_notifications_for_operation(operation_id)
        return result

    def _x_cut_document(*, cut_id: str, branch_id: str,
                        actor_user_id: str) -> CashPrintDocument:
        cut = query_services["x_cut"].get(
            cut_id=cut_id,
            branch_id=branch_id,
            requester_user_id=actor_user_id,
        )
        fields = (
            ("Turno", cut.shift_id),
            ("Generado por", cut.generated_by),
            ("Generado", cut.generated_at),
            ("Final", "No"),
        )
        totals = ()
        if cut.sensitive_amounts_visible:
            totals = (("Efectivo esperado", f"{cut.expected_cash:.2f}"),)
        return CashPrintDocument(
            document_type=CashPrintDocumentType.X_CUT,
            entity_id=cut.id,
            branch_id=branch_id,
            reference=cut.document_number,
            title="Corte X",
            fields=fields,
            lines=tuple(
                (key, value)
                for key, value in sorted((cut.snapshot or {}).items())
                if key.startswith("movement.")
            ),
            totals=totals,
            qr_value=cut.id,
            final=False,
        )

    def _print_cash_cut(*, document, document_type, route_document: str, label: str,
                        cut_id: str, branch_id: str, actor_user_id: str, reprint: bool,
                        original_print_id: str | None, reprint_reason: str | None) -> str:
        """Imprime de verdad (CASH-26 bloque 2): impresora de Document Output,
        ESC/POS al ancho del papel, cola confirmada y despacho inmediato. Sólo
        devuelve si salió papel; si no, el trabajo queda FALLIDO con su motivo
        y se puede reimprimir."""
        resolved_original_print_id = original_print_id
        if reprint and not resolved_original_print_id:
            resolved_original_print_id = print_repository.latest_print_id_for_document(
                entity_id=cut_id, document_type=document_type)
        if reprint and not resolved_original_print_id:
            raise ValueError(f"No existe una impresion original para reimprimir este {label}")
        try:
            printer_id, paper_width = resolve_cash_printer(
                connection, route_document, branch_id=branch_id,
                workstation_id=str(getattr(session, "workstation_id", "") or "") or None)
        except PrintTargetUnavailable as exc:
            raise CashConfigurationError(str(exc)) from exc
        print_id = PrintCashDocumentUseCase(
            authorization=authorization,
            renderers={CashPrintFormat.ESC_POS: CashDocumentEscPosRenderer(
                paper_width_mm=paper_width)},
            queue=print_repository, audit=print_repository,
        ).execute(PrintCashDocumentCommand(
            operation_id=new_uuid(), actor_user_id=actor_user_id, document=document,
            printer_id=printer_id, output_format=CashPrintFormat.ESC_POS,
            original_print_id=resolved_original_print_id if reprint else None,
            reprint_reason=reprint_reason if reprint else None,
        ))
        connection.commit()
        DispatchCashPrintQueueUseCase(
            authorization=authorization, store=print_repository, gateway=print_gateway,
        ).execute(branch_id=branch_id, actor_user_id=actor_user_id)
        connection.commit()
        status, error = print_repository.delivery_status(print_id)
        if status != "PRINTED":
            raise CashInvalidStateError(
                f"El {label} quedó registrado pero no se imprimió: {error or status}")
        return print_id

    def print_x_cut_handler(
        *,
        cut_id: str,
        branch_id: str,
        actor_user_id: str,
        reprint: bool = False,
        original_print_id: str | None = None,
        reprint_reason: str | None = None,
    ):
        authorization.require(
            user_id=actor_user_id,
            permission_code=CashPermissions.X_CUT_REPRINT if reprint else CashPermissions.X_CUT_PRINT,
            branch_id=branch_id,
        )
        document = _x_cut_document(
            cut_id=cut_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
        )
        return _print_cash_cut(
            document=document, document_type=CashPrintDocumentType.X_CUT,
            route_document=DocumentType.X_REPORT.value, label="Corte X",
            cut_id=cut_id, branch_id=branch_id, actor_user_id=actor_user_id,
            reprint=reprint, original_print_id=original_print_id,
            reprint_reason=reprint_reason)

    def generate_z_cut_handler(
        *,
        shift_id: str,
        branch_id: str,
        actor_user_id: str,
    ):
        operation_id = new_uuid()
        result = use_cases["cash_generate_z_cut_uc"].execute(
            connection,
            shift_id=shift_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
        )
        prepare_notifications_for_operation(operation_id)
        prepare_notifications_for_entity(getattr(result, "difference_id", None))
        return result

    def _z_cut_document(*, cut_id: str, branch_id: str,
                        actor_user_id: str) -> CashPrintDocument:
        cut = query_services["z_cut"].get(
            cut_id=cut_id,
            branch_id=branch_id,
            requester_user_id=actor_user_id,
        )
        totals = ()
        if cut.sensitive_amounts_visible:
            totals = (
                ("Efectivo esperado", f"{cut.expected_cash:.2f}"),
                ("Efectivo contado", f"{cut.counted_cash:.2f}"),
                ("Diferencia", f"{cut.difference:.2f}"),
            )
        return CashPrintDocument(
            document_type=CashPrintDocumentType.Z_CUT,
            entity_id=cut.id,
            branch_id=cut.branch_id,
            reference=cut.document_number,
            title="Corte Z",
            fields=(
                ("Turno", cut.shift_id),
                ("Conteo ciego", cut.blind_count_id or "-"),
                ("Generado por", cut.generated_by),
                ("Generado", cut.generated_at),
                ("Final", "Si" if cut.is_final else "No"),
            ),
            totals=totals,
            qr_value=cut.id,
            final=cut.is_final,
        )

    def print_z_cut_handler(
        *,
        cut_id: str,
        branch_id: str,
        actor_user_id: str,
        reprint: bool = False,
        original_print_id: str | None = None,
        reprint_reason: str | None = None,
    ):
        authorization.require(
            user_id=actor_user_id,
            permission_code=CashPermissions.Z_CUT_REPRINT if reprint else CashPermissions.Z_CUT_PRINT,
            branch_id=branch_id,
        )
        document = _z_cut_document(
            cut_id=cut_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
        )
        return _print_cash_cut(
            document=document, document_type=CashPrintDocumentType.Z_CUT,
            route_document=DocumentType.Z_REPORT.value, label="Corte Z",
            cut_id=cut_id, branch_id=branch_id, actor_user_id=actor_user_id,
            reprint=reprint, original_print_id=original_print_id,
            reprint_reason=reprint_reason)

    def notify_z_cut_handler(
        *,
        cut_id: str,
        branch_id: str,
        actor_user_id: str,
    ):
        operation_id = new_uuid()
        result = use_cases["cash_notify_z_cut_uc"].execute(
            connection,
            cut_id=cut_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
        )
        prepare_notifications_for_operation(operation_id)
        return result

    def set_cash_sync_connectivity_handler(
        *,
        device_id: str,
        branch_id: str,
        actor_user_id: str,
        online: bool,
    ):
        _ensure_cash_sync_device(connection, device_id=device_id, branch_id=branch_id)
        return use_cases["cash_sync_connectivity_uc"].execute(
            connection,
            device_id=device_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            online=online,
        )

    def resolve_cash_sync_conflict_handler(
        *,
        envelope_id: str,
        strategy: str,
        reason: str,
        branch_id: str,
        actor_user_id: str,
    ):
        operation_id = new_uuid()
        result = use_cases["cash_sync_conflict_resolution_uc"].execute(
            connection,
            envelope_id=envelope_id,
            strategy=strategy,
            reason=reason,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
        )
        prepare_notifications_for_operation(operation_id)
        return result

    def run_cash_sync_cycle_handler(
        *,
        device_id: str,
        branch_id: str,
        actor_user_id: str,
    ):
        authorization.require(
            user_id=actor_user_id,
            permission_code=CashPermissions.SYNC_MANAGE,
            branch_id=branch_id,
        )
        _ensure_cash_sync_device(connection, device_id=device_id, branch_id=branch_id)
        return use_cases["cash_sync_service"].synchronize(
            connection,
            device_id=device_id,
            branch_id=branch_id,
        )

    def dispatch_cash_notifications_handler(
        *,
        branch_id: str,
        actor_user_id: str,
    ):
        authorization.require(
            user_id=actor_user_id,
            permission_code=CashPermissions.NOTIFICATIONS_MANAGE,
            branch_id=branch_id,
        )
        return use_cases["cash_dispatch_notifications_uc"].execute(connection)

    def verify_authorizer_handler(*, username: str, password: str) -> str:
        """El autorizador se prueba con SU clave (mismas reglas y bloqueo que el
        login); devuelve su id. El permiso lo revalida cada caso de uso."""
        try:
            return build_authorizer_credentials_verifier(connection).execute(
                username=username, password=password,
                workstation_id=str(getattr(session, "workstation_id", "") or ""))
        except AuthenticationFailedError as exc:
            raise CashAuthorizationRequiredError(str(exc)) from exc

    command_handlers = {
        "verify_authorizer": verify_authorizer_handler,
        "open_cash_shift": open_cash_shift_handler,
        "suspend_cash_shift": suspend_cash_shift_handler,
        "resume_cash_shift": resume_cash_shift_handler,
        "begin_cash_shift_closing": begin_cash_shift_closing_handler,
        "configure_cash_catalog": configure_cash_catalog_handler,
        "deactivate_cash_configuration": deactivate_cash_configuration_handler,
        "add_cash_alert_recipient": add_cash_alert_recipient_handler,
        "deactivate_cash_alert_recipient": deactivate_cash_alert_recipient_handler,
        "create_cash_device": create_cash_device_handler,
        "set_cash_device_status": set_cash_device_status_handler,
        "diagnose_cash_hardware": diagnose_cash_hardware_handler,
        "open_cash_drawer_hardware": open_cash_drawer_hardware_handler,
        "start_blind_count": start_blind_count_handler,
        "capture_blind_count_denomination": capture_blind_count_denomination_handler,
        "confirm_blind_count": confirm_blind_count_handler,
        "register_cash_movement": register_cash_movement_handler,
        "reverse_cash_movement": reverse_cash_movement_handler,
        "prepare_cash_handover": prepare_cash_handover_handler,
        "deliver_cash_handover": deliver_cash_handover_handler,
        "receive_cash_handover": receive_cash_handover_handler,
        "dispute_cash_handover": dispute_cash_handover_handler,
        "explain_cash_difference": explain_cash_difference_handler,
        "review_cash_difference": review_cash_difference_handler,
        "resolve_cash_difference": resolve_cash_difference_handler,
        "generate_x_cut": generate_x_cut_handler,
        "print_x_cut": print_x_cut_handler,
        "generate_z_cut": generate_z_cut_handler,
        "print_z_cut": print_z_cut_handler,
        "notify_z_cut": notify_z_cut_handler,
        "set_cash_sync_connectivity": set_cash_sync_connectivity_handler,
        "resolve_cash_sync_conflict": resolve_cash_sync_conflict_handler,
        "run_cash_sync_cycle": run_cash_sync_cycle_handler,
        "dispatch_cash_notifications": dispatch_cash_notifications_handler,
    }
    def deliver_notifications() -> None:
        use_cases["cash_dispatch_notifications_uc"].execute(connection)
        connection.commit()

    command_handlers = {
        name: (handler if name == "verify_authorizer"
               else _after_cash_command(connection, handler, deliver_notifications))
        for name, handler in command_handlers.items()
    }

    operational_context = DesktopCashOperationalContextResolver(
        connection,
        session,
        composition_root,
    )

    def active_context() -> dict[str, object | None]:
        return operational_context.context().as_presenter_dict()

    return CashRegisterPresenter(
        session_context=session,
        query_services=query_services,
        use_cases=use_cases,
        command_handlers=command_handlers,
        active_context_provider=active_context,
        active_shift_provider=operational_context.active_shift_id,
        active_count_context_provider=operational_context.active_count_context,
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
