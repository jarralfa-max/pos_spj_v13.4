"""Desktop composition root for the canonical Losses workspace.

Una sola composición sirve a los DOS anfitriones del módulo: el slot `MERMAS`
de `MainWindow` (vía `LossesModuleHost`) y el shell canónico (vía
`create_losses_view`, que llama `LossesModuleActivator`). §3 prohíbe que cada
uno arme el suyo.
"""

from typing import Callable, Mapping, NamedTuple

from backend.application.losses.authorization import LossAuthorizationPolicy
from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.register_general_loss import RegisterGeneralLossUseCase
from backend.application.losses.loss_inventory_integration import LossInventoryIntegrationService
from backend.application.losses.production_loss import ProductionLossAnalysisService
from backend.application.losses.yield_queries import YieldMonitoringQueryService
from backend.application.losses.expiry_damage import ExpiryDamageWorkflowService
from backend.application.losses.quality_control import QualityInspectionService
from backend.application.losses.transfer_integration import TransferLossIntegrationService
from backend.application.losses.recovery import LossRecoveryService
from backend.application.losses.disposition import LossDispositionService
from backend.application.losses.investigation import LossInvestigationService
from backend.application.losses.root_cause import LossRootCauseService
from backend.application.losses.root_cause_queries import LossRootCauseQueryService
from backend.application.losses.corrective_action import LossCorrectiveActionService
from backend.application.losses.valuation import LossValuationService
from backend.application.losses.notifications import LossNotificationRouter
from backend.application.losses.analytics import LossAnalyticsQueryService
from backend.application.transfers.integrations.outbound_handlers import TransferLossCaseRequestedHandler
from backend.application.event_handlers.losses import ProductionCompletedLossHandler
from backend.application.losses.session_authorization import LossSessionPermissionChecker
from backend.application.inventory.composition import InventoryUseCaseFactory
from backend.infrastructure.integrations.losses_inventory_gateway import LossesInventoryGateway
from backend.infrastructure.persistence.loss_inventory_repository import LossInventoryRepository
from backend.infrastructure.persistence.expiry_damage_repository import ExpiryDamageRepository
from backend.infrastructure.persistence.quality_control_repository import QualityControlRepository
from backend.infrastructure.persistence.transfer_loss_repository import TransferLossRepository
from backend.infrastructure.persistence.loss_recovery_repository import LossRecoveryRepository
from backend.infrastructure.persistence.loss_disposition_repository import LossDispositionRepository
from backend.infrastructure.persistence.loss_investigation_repository import LossInvestigationRepository
from backend.infrastructure.persistence.loss_root_cause_repository import LossRootCauseQueryRepository, LossRootCauseRepository
from backend.infrastructure.persistence.loss_corrective_action_repository import LossCorrectiveActionRepository
from backend.infrastructure.persistence.loss_valuation_repository import LossValuationRepository
from backend.infrastructure.persistence.loss_notification_repository import LossNotificationRepository
from backend.infrastructure.persistence.loss_analytics_repository import LossAnalyticsRepository
from backend.infrastructure.integrations.loss_notification_senders import (LossInAppNotificationSender,
    LossWhatsAppNotificationSender,UnavailableWhatsAppNotificationSender)
from backend.infrastructure.persistence.production_loss_repository import ProductionLossRepository
from backend.infrastructure.persistence.losses_registration_repository import LossRegistrationQueryRepository, LossRegistrationRepository
from frontend.desktop.modules.losses.losses_routes import build_page
from frontend.desktop.modules.losses.losses_view import LossesView
from frontend.desktop.modules.losses.pages import LossAnalyticsPage, LossRegistrationPage, RootCausePage
from frontend.desktop.modules.losses.presenters.root_cause_presenter import RootCausePresenter
from frontend.desktop.modules.losses.presenters.analytics_presenter import LossAnalyticsPresenter
from frontend.desktop.modules.losses.presenters import LossRegistrationPresenter


class LossesWiring(NamedTuple):
    """Todo lo que el workspace de Mermas necesita, compuesto UNA sola vez."""

    has_permission: Callable[[str], bool]
    page_builder: Callable[[str], object]
    services: Mapping[str, object]


def _resolve_warehouse_id(session) -> str:
    """`SessionContext` y `LegacySessionAdapter` exponen `active_warehouse_id`;
    NINGUNO define `warehouse_id`. Leer sólo el segundo devolvía siempre "":
    almacén vacío en el formulario de registro y `allowed_warehouse_ids={""}`
    en el scope de autorización — el "inventar contexto" que §17 prohíbe.

    Mismo orden de resolución que ya usan `inventory/presenter.py`,
    `purchasing/*_presenter.py` y el `ProcessingOrderPresenter` del módulo
    hermano: canónico primero, alias legacy después.
    """
    return str(
        getattr(session, "active_warehouse_id", None)
        or getattr(session, "warehouse_id", None)
        or ""
    )


def _permission_checker(session) -> Callable[[str], bool]:
    """Las dos sesiones vivas —`SessionContext` y `LegacySessionAdapter`—
    exponen `tiene_permiso`/`permisos`, nunca `has_permission`/`permissions`.

    Sin sesión no se concede nada: este callback gobierna el sidebar interno
    del módulo y mostrar de más sería peor que mostrar de menos.
    """
    if session is None:
        return lambda _permission: False
    checker = getattr(session, "tiene_permiso", None)
    if callable(checker):
        return lambda permission: bool(checker(permission))

    def _from_permission_codes(permission: str) -> bool:
        codes = getattr(session, "permisos", None)
        if codes is None:
            return False
        granted = {str(code).upper() for code in codes}
        return "*" in granted or permission.upper() in granted

    return _from_permission_codes


def build_losses_wiring(
    connection, session=None, *, whatsapp_message_service=None,
) -> LossesWiring:
    """ÚNICA composición del workspace de Mermas (§3: una sola ruta funcional).

    Recibe sólo lo que necesita —conexión y sesión ya desempaquetadas—, nunca
    el `AppContainer`, igual que `create_fidelidad_view` y las demás funciones
    de composición ya migradas.
    """
    has_permission = _permission_checker(session)
    authorization = LossAuthorizationPolicy(LossSessionPermissionChecker(session))
    warehouse_id = _resolve_warehouse_id(session)

    def context_provider():
        actor = str(getattr(session, "user_id", "") or "")
        branch = str(getattr(session, "active_branch_id", "") or "")
        permissions = frozenset(
            code for code in getattr(session, "permisos", ())
            if isinstance(code, str))
        return LossExecutionContext(
            actor_user_id=actor, active_branch_id=branch,
            assigned_branch_ids=frozenset({branch}),
            allowed_warehouse_ids=frozenset({warehouse_id}),
            permissions=permissions,
        )

    presenter = LossRegistrationPresenter(
        LossRegistrationQueryRepository(connection),
        RegisterGeneralLossUseCase(LossRegistrationRepository(connection), authorization),
        context_provider,
    )
    inventory_factory = InventoryUseCaseFactory.from_session(session)
    inventory_gateway = LossesInventoryGateway(
            connection, inventory_factory.post_movement(),
            inventory_factory.reverse_movement(),
            inventory_factory.quarantine_stock(),
            inventory_factory.release_quarantine(),
            inventory_factory.dispose_quarantine(),
            inventory_factory.record_temperature_reading())
    whatsapp_sender = (LossWhatsAppNotificationSender(whatsapp_message_service)
                       if whatsapp_message_service is not None
                       else UnavailableWhatsAppNotificationSender())
    transfer_loss_service = TransferLossIntegrationService(
        TransferLossRepository(connection), authorization,
        context_provider=context_provider)
    production_repository = ProductionLossRepository(connection)
    production_loss_service = ProductionLossAnalysisService(
        production_repository, authorization)

    services = {
        "loss_inventory_service": LossInventoryIntegrationService(
            LossInventoryRepository(connection), inventory_gateway, authorization),
        "expiry_damage_service": ExpiryDamageWorkflowService(
            ExpiryDamageRepository(connection), inventory_gateway, authorization),
        "quality_inspection_service": QualityInspectionService(
            QualityControlRepository(connection), inventory_gateway, authorization),
        "loss_recovery_service": LossRecoveryService(
            LossRecoveryRepository(connection), inventory_gateway, authorization),
        "loss_disposition_service": LossDispositionService(
            LossDispositionRepository(connection), inventory_gateway, authorization),
        "loss_investigation_service": LossInvestigationService(
            LossInvestigationRepository(connection), authorization),
        "loss_root_cause_service": LossRootCauseService(
            LossRootCauseRepository(connection), authorization),
        "loss_corrective_action_service": LossCorrectiveActionService(
            LossCorrectiveActionRepository(connection), authorization),
        "loss_valuation_service": LossValuationService(
            LossValuationRepository(connection), authorization),
        "loss_notification_router": LossNotificationRouter(
            LossNotificationRepository(connection), LossInAppNotificationSender(),
            whatsapp_sender),
        "transfer_loss_service": transfer_loss_service,
        "transfer_loss_requested_handler": TransferLossCaseRequestedHandler(
            transfer_loss_service),
        "production_loss_service": production_loss_service,
        "yield_monitoring_query_service": YieldMonitoringQueryService(
            production_repository),
        "production_completed_loss_handler": ProductionCompletedLossHandler(
            production_loss_service, context_provider),
    }

    analytics_presenter = LossAnalyticsPresenter(
        LossAnalyticsQueryService(LossAnalyticsRepository(connection), authorization),
        context_provider)
    root_cause_presenter = RootCausePresenter(
        LossRootCauseQueryService(LossRootCauseQueryRepository(connection)),
        services["loss_root_cause_service"], context_provider)

    def page_builder(page_id: str):
        if page_id == "losses_registration":
            return LossRegistrationPage(presenter, warehouse_id=warehouse_id)
        if page_id == "losses_investigations":
            return RootCausePage(root_cause_presenter)
        if page_id in ("losses_overview", "losses_analysis"):
            return LossAnalyticsPage(analytics_presenter)
        return build_page(page_id)

    return LossesWiring(has_permission, page_builder, services)


def _attach_services(view: LossesView, services: Mapping[str, object]) -> LossesView:
    for name, service in services.items():
        setattr(view, name, service)
    return view


def create_losses_view(
    connection, session=None, *, whatsapp_message_service=None,
    badges=None, parent=None,
) -> LossesView:
    """Factory que consume el shell nuevo (`LossesModuleActivator`).

    Antes el activator construía `LossesView(page_builder=build_page)` por su
    cuenta: sin servicios, sin presenters y con las 16 rutas en placeholder,
    incluidas las 4 que SÍ tienen página real. Eran dos composiciones del
    mismo dominio y la del shell era estrictamente peor (§3).
    """
    wiring = build_losses_wiring(
        connection, session, whatsapp_message_service=whatsapp_message_service)
    view = LossesView(
        has_permission=wiring.has_permission, badges=badges,
        page_builder=wiring.page_builder, parent=parent)
    return _attach_services(view, wiring.services)


class LossesModuleHost(LossesView):
    """Adaptador del `AppContainer` legacy para el slot `MERMAS` de
    `MainWindow`: desempaqueta el contenedor y delega en `build_losses_wiring`.
    NO compone nada por su cuenta (§4: los adapters traducen, no implementan).
    """

    def __init__(self, container, parent=None) -> None:
        wiring = build_losses_wiring(
            container.db,
            getattr(container, "session", None),
            whatsapp_message_service=getattr(container, "whatsapp_message_service", None),
        )
        super().__init__(
            has_permission=wiring.has_permission,
            badges=self._load_badges(container),
            page_builder=wiring.page_builder,
            parent=parent,
        )
        _attach_services(self, wiring.services)

    @staticmethod
    def _load_badges(container) -> dict[str, int]:
        service = getattr(container, "losses_navigation_query_service", None)
        if service is None or not hasattr(service, "get_badges"):
            return {}
        branch_id = str(getattr(container, "sucursal_id", "") or "")
        values = service.get_badges(branch_id=branch_id)
        return {str(key): max(0, int(value or 0)) for key, value in dict(values).items()}
