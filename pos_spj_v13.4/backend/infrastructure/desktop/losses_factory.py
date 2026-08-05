"""Desktop composition root for the canonical Losses workspace."""

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


class LossesModuleHost(LossesView):
    def __init__(self, container, parent=None) -> None:
        session = getattr(container, "session", None)
        has_permission = (
            session.tiene_permiso
            if session is not None and hasattr(session, "tiene_permiso")
            else lambda _permission: False
        )
        badges = self._load_badges(container)

        write_repository = LossRegistrationRepository(container.db)
        query_repository = LossRegistrationQueryRepository(container.db)
        authorization = LossAuthorizationPolicy(LossSessionPermissionChecker(session))

        def context_provider():
            actor = str(getattr(session, "user_id", "") or "")
            branch = str(getattr(session, "active_branch_id", "") or "")
            warehouse = str(getattr(session, "warehouse_id", "") or "")
            permissions = frozenset(
                code for code in getattr(session, "permisos", ())
                if isinstance(code, str))
            return LossExecutionContext(
                actor_user_id=actor, active_branch_id=branch,
                assigned_branch_ids=frozenset({branch}),
                allowed_warehouse_ids=frozenset({warehouse}),
                permissions=permissions,
            )

        presenter = LossRegistrationPresenter(
            query_repository,
            RegisterGeneralLossUseCase(write_repository, authorization),
            context_provider,
        )
        inventory_factory = InventoryUseCaseFactory.from_session(session)
        inventory_gateway = LossesInventoryGateway(
                container.db, inventory_factory.post_movement(),
                inventory_factory.reverse_movement(),
                inventory_factory.quarantine_stock(),
                inventory_factory.release_quarantine(),
                inventory_factory.dispose_quarantine(),
                inventory_factory.record_temperature_reading())
        self.loss_inventory_service = LossInventoryIntegrationService(
            LossInventoryRepository(container.db),
            inventory_gateway,
            authorization,
        )
        self.expiry_damage_service = ExpiryDamageWorkflowService(
            ExpiryDamageRepository(container.db), inventory_gateway, authorization)
        self.quality_inspection_service = QualityInspectionService(
            QualityControlRepository(container.db), inventory_gateway, authorization)
        self.loss_recovery_service = LossRecoveryService(
            LossRecoveryRepository(container.db), inventory_gateway, authorization)
        self.loss_disposition_service = LossDispositionService(
            LossDispositionRepository(container.db), inventory_gateway, authorization)
        self.loss_investigation_service = LossInvestigationService(
            LossInvestigationRepository(container.db), authorization)
        self.loss_root_cause_service = LossRootCauseService(
            LossRootCauseRepository(container.db), authorization)
        self.loss_corrective_action_service = LossCorrectiveActionService(
            LossCorrectiveActionRepository(container.db), authorization)
        self.loss_valuation_service = LossValuationService(
            LossValuationRepository(container.db), authorization)
        whatsapp_service = getattr(container, "whatsapp_message_service", None)
        whatsapp_sender = (LossWhatsAppNotificationSender(whatsapp_service)
                           if whatsapp_service is not None
                           else UnavailableWhatsAppNotificationSender())
        self.loss_notification_router = LossNotificationRouter(
            LossNotificationRepository(container.db), LossInAppNotificationSender(),
            whatsapp_sender)
        analytics_presenter = LossAnalyticsPresenter(
            LossAnalyticsQueryService(LossAnalyticsRepository(container.db), authorization),
            context_provider)
        root_cause_presenter = RootCausePresenter(
            LossRootCauseQueryService(LossRootCauseQueryRepository(container.db)),
            self.loss_root_cause_service, context_provider)
        self.transfer_loss_service = TransferLossIntegrationService(
            TransferLossRepository(container.db), authorization,
            context_provider=context_provider)
        self.transfer_loss_requested_handler = TransferLossCaseRequestedHandler(
            self.transfer_loss_service)
        production_repository = ProductionLossRepository(container.db)
        self.production_loss_service = ProductionLossAnalysisService(
            production_repository, authorization)
        self.yield_monitoring_query_service = YieldMonitoringQueryService(
            production_repository)
        self.production_completed_loss_handler = ProductionCompletedLossHandler(
            self.production_loss_service, context_provider)
        warehouse_id = str(getattr(session, "warehouse_id", "") or "")

        def page_builder(page_id: str):
            if page_id == "losses_registration":
                return LossRegistrationPage(presenter, warehouse_id=warehouse_id)
            if page_id == "losses_investigations":
                return RootCausePage(root_cause_presenter)
            if page_id in ("losses_overview", "losses_analysis"):
                return LossAnalyticsPage(analytics_presenter)
            return build_page(page_id)

        super().__init__(
            has_permission=has_permission,
            badges=badges,
            page_builder=page_builder,
            parent=parent,
        )

    @staticmethod
    def _load_badges(container) -> dict[str, int]:
        service = getattr(container, "losses_navigation_query_service", None)
        if service is None or not hasattr(service, "get_badges"):
            return {}
        branch_id = str(getattr(container, "sucursal_id", "") or "")
        values = service.get_badges(branch_id=branch_id)
        return {str(key): max(0, int(value or 0)) for key, value in dict(values).items()}
