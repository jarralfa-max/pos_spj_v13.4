"""Canonical route registry for the Configuración internal sidebar.
Mirrors `frontend/desktop/modules/transfers/transfers_routes.py`.
"""
from __future__ import annotations

from .navigation.configuracion_sidebar import CONFIGURACION_NAV

CONFIGURACION_ROUTE_IDS = frozenset(entry.page_id for entry in CONFIGURACION_NAV)


def build_page(page_id: str, presenter):
    """Build one canonical page; unknown route IDs are rejected."""
    if page_id not in CONFIGURACION_ROUTE_IDS:
        raise KeyError(f"Unknown Configuración route: {page_id}")
    from .pages import PAGE_CLASSES
    return PAGE_CLASSES[page_id](presenter)


def create_configuracion_view(container, parent=None):
    """Factory used by the legacy `MainWindow`/`menu_lateral` navigation
    (via `modulos/configuracion_workspace.py`) — mirrors
    `frontend/desktop/modules/finance/finance_routes.py::create_finance_view`.
    Extracts only what the module needs from `AppContainer`, never the
    whole container. Uses `getattr(container, "session", None)` — NOT
    `"session_context"`, an attribute that doesn't exist on
    `AppContainer` (`core/app_container.py` sets `self.session`); finance/
    hr's own wrappers still have that exact bug.
    """
    from backend.application.queries.configuracion.workspace_query_service import (
        ConfiguracionWorkspaceQueryService,
    )
    from backend.application.use_cases.configuracion.feature_flag_change_request_use_cases import (
        ApplyFeatureFlagChangeRequestUseCase,
        ApproveFeatureFlagChangeRequestUseCase,
        RejectFeatureFlagChangeRequestUseCase,
    )
    from backend.application.use_cases.configuracion.device_management_use_cases import (
        ChangeDeviceStatusUseCase,
        RegisterDeviceProfileUseCase,
        RegisterDeviceUseCase,
        UpdateDeviceUseCase,
    )
    from backend.application.use_cases.configuracion.document_template_use_cases import (
        ChangeDocumentTemplateStatusUseCase,
        ChangeTemplateVersionStatusUseCase,
        CreateDocumentTemplateUseCase,
        CreateNextTemplateVersionUseCase,
        UpdateDocumentTemplateUseCase,
    )
    from backend.application.use_cases.configuracion.marketing_campaign_use_cases import (
        ChangeMarketingCampaignStatusUseCase,
        CreateMarketingCampaignUseCase,
        UpdateMarketingCampaignUseCase,
    )
    from backend.application.use_cases.configuracion.customer_display_advertising_use_cases import (
        AssignCampaignPlacementUseCase,
        ChangeAdvertisingSlotStatusUseCase,
        ChangeContentCampaignStatusUseCase,
        ChangeContentStatusUseCase,
        CreateAdvertisingSlotUseCase,
        CreateContentCampaignUseCase,
        CreateContentUseCase,
        UnassignCampaignPlacementUseCase,
        UpdateAdvertisingSlotUseCase,
        UpdateContentCampaignUseCase,
        UpdateContentUseCase,
    )
    from backend.application.use_cases.configuracion.integration_management_use_cases import (
        ChangeIntegrationDefinitionStatusUseCase,
        ChangeIntegrationInstanceStatusUseCase,
        ChangeWebhookEndpointStatusUseCase,
        CreateIntegrationDefinitionUseCase,
        CreateIntegrationInstanceUseCase,
        CreateWebhookEndpointUseCase,
        RecordIntegrationHealthCheckUseCase,
        SetIntegrationInstanceCredentialUseCase,
        UpdateIntegrationDefinitionUseCase,
        UpdateIntegrationInstanceUseCase,
    )
    from backend.application.use_cases.configuracion.notification_management_use_cases import (
        ChangeNotificationAccountStatusUseCase,
        ChangeNotificationRouteStatusUseCase,
        ChangeNotificationTemplateStatusUseCase,
        CreateNotificationAccountUseCase,
        CreateNotificationRouteUseCase,
        CreateNotificationTemplateUseCase,
        UpdateNotificationAccountUseCase,
        UpdateNotificationTemplateUseCase,
    )
    from backend.application.use_cases.configuracion.feature_flag_management_use_cases import (
        ChangeFeatureFlagStatusUseCase,
        CreateFeatureFlagUseCase,
        RequestFeatureFlagChangeUseCase,
        UpdateFeatureFlagUseCase,
    )
    from backend.application.use_cases.configuracion.appearance_management_use_cases import (
        ChangeAppearancePreferenceStatusUseCase,
        ChangeDensityProfileStatusUseCase,
        ChangeThemeStatusUseCase,
        CreateAppearancePreferenceUseCase,
        CreateDensityProfileUseCase,
        CreateDesignTokenUseCase,
        CreateThemeUseCase,
        UpdateDensityProfileUseCase,
        UpdateDesignTokenUseCase,
        UpdateThemeUseCase,
    )
    from backend.application.use_cases.configuracion.offline_management_use_cases import (
        ChangeCacheExpirationPolicyStatusUseCase,
        CreateCacheExpirationPolicyUseCase,
        UpdateCacheExpirationPolicyUseCase,
    )
    from backend.application.use_cases.save_user_use_case import SaveUserUseCase
    from backend.application.use_cases.set_user_active_use_case import SetUserActiveUseCase
    from backend.application.use_cases.save_role_use_case import SaveRoleUseCase
    from backend.application.use_cases.set_installation_branch_use_case import (
        SetInstallationBranchUseCase,
    )
    from core.services.configuration_settings_service import (
        CompanyProfileService,
        PermissionQueryService,
        RoleManagementService,
        UserManagementService,
    )
    from backend.application.services.user_security_service import UserSecurityService
    from repositories.config_repository import ConfigRepository
    from backend.security.secrets.default_secret_store import build_default_secret_store
    from backend.application.use_cases.configuracion.company_branch_use_cases import (
        RegisterBranchProfileUseCase,
        SaveCompanyProfileUseCase,
        UpdateBranchProfileUseCase,
    )
    from backend.application.use_cases.configuracion.set_default_theme_use_case import (
        SetDefaultThemeUseCase,
    )
    from backend.application.use_cases.configuracion.workstation_use_cases import (
        ChangeWorkstationStatusUseCase,
        RegisterWorkstationUseCase,
        UpdateWorkstationUseCase,
    )
    from backend.application.use_cases.configuracion.device_assignment_use_cases import (
        AssignDeviceUseCase,
        UnassignDeviceUseCase,
    )
    from backend.application.use_cases.configuracion.print_route_use_cases import (
        ChangePrintRouteStatusUseCase,
        CreatePrintRouteUseCase,
        UpdatePrintRouteUseCase,
    )
    from backend.application.configuracion.authorization import (
        ConfiguracionAuthorizationPolicy,
        SessionPermissionChecker,
    )
    from backend.infrastructure.db.repositories.settings.configuracion_security_repositories import (
        ConfiguracionAuditLogRepository,
    )
    from core.permissions import verificar_permiso
    from frontend.desktop.modules.configuracion.configuracion_presenter import ConfiguracionPresenter
    from frontend.desktop.modules.configuracion.configuracion_view import ConfiguracionView

    connection = getattr(container, "db", None)
    session = getattr(container, "session", None)
    secret_store = build_default_secret_store()
    query_service = ConfiguracionWorkspaceQueryService(connection, secret_store)
    authorization = ConfiguracionAuthorizationPolicy(SessionPermissionChecker(session))
    config_repository = ConfigRepository(connection)
    user_management_service = UserManagementService(config_repository)
    role_management_service = RoleManagementService(config_repository)
    permission_query_service = PermissionQueryService(config_repository)
    company_profile_service = CompanyProfileService(config_repository)
    user_security_service = UserSecurityService(
        connection, permission_checker=session.tiene_permiso if session is not None else None)
    presenter = ConfiguracionPresenter(
        query_service, session_context=session,
        authorization=authorization,
        audit_log_repository=ConfiguracionAuditLogRepository(connection),
        approve_change_request_uc=ApproveFeatureFlagChangeRequestUseCase(connection),
        reject_change_request_uc=RejectFeatureFlagChangeRequestUseCase(connection),
        apply_change_request_uc=ApplyFeatureFlagChangeRequestUseCase(connection),
        set_default_theme_uc=SetDefaultThemeUseCase(connection),
        register_device_profile_uc=RegisterDeviceProfileUseCase(connection),
        register_device_uc=RegisterDeviceUseCase(connection),
        update_device_uc=UpdateDeviceUseCase(connection),
        change_device_status_uc=ChangeDeviceStatusUseCase(connection),
        create_document_template_uc=CreateDocumentTemplateUseCase(connection),
        create_next_template_version_uc=CreateNextTemplateVersionUseCase(connection),
        change_template_version_status_uc=ChangeTemplateVersionStatusUseCase(connection),
        save_company_profile_uc=SaveCompanyProfileUseCase(connection),
        register_branch_profile_uc=RegisterBranchProfileUseCase(connection),
        update_branch_profile_uc=UpdateBranchProfileUseCase(connection),
        register_workstation_uc=RegisterWorkstationUseCase(connection),
        update_workstation_uc=UpdateWorkstationUseCase(connection),
        change_workstation_status_uc=ChangeWorkstationStatusUseCase(connection),
        assign_device_uc=AssignDeviceUseCase(connection),
        unassign_device_uc=UnassignDeviceUseCase(connection),
        create_print_route_uc=CreatePrintRouteUseCase(connection),
        update_print_route_uc=UpdatePrintRouteUseCase(connection),
        change_print_route_status_uc=ChangePrintRouteStatusUseCase(connection),
        update_document_template_uc=UpdateDocumentTemplateUseCase(connection),
        change_document_template_status_uc=ChangeDocumentTemplateStatusUseCase(connection),
        create_marketing_campaign_uc=CreateMarketingCampaignUseCase(connection),
        update_marketing_campaign_uc=UpdateMarketingCampaignUseCase(connection),
        change_marketing_campaign_status_uc=ChangeMarketingCampaignStatusUseCase(connection),
        create_content_uc=CreateContentUseCase(connection),
        update_content_uc=UpdateContentUseCase(connection),
        change_content_status_uc=ChangeContentStatusUseCase(connection),
        create_content_campaign_uc=CreateContentCampaignUseCase(connection),
        update_content_campaign_uc=UpdateContentCampaignUseCase(connection),
        change_content_campaign_status_uc=ChangeContentCampaignStatusUseCase(connection),
        create_advertising_slot_uc=CreateAdvertisingSlotUseCase(connection),
        update_advertising_slot_uc=UpdateAdvertisingSlotUseCase(connection),
        change_advertising_slot_status_uc=ChangeAdvertisingSlotStatusUseCase(connection),
        assign_campaign_placement_uc=AssignCampaignPlacementUseCase(connection),
        unassign_campaign_placement_uc=UnassignCampaignPlacementUseCase(connection),
        create_integration_definition_uc=CreateIntegrationDefinitionUseCase(connection),
        update_integration_definition_uc=UpdateIntegrationDefinitionUseCase(connection),
        change_integration_definition_status_uc=ChangeIntegrationDefinitionStatusUseCase(connection),
        create_integration_instance_uc=CreateIntegrationInstanceUseCase(connection),
        update_integration_instance_uc=UpdateIntegrationInstanceUseCase(connection),
        change_integration_instance_status_uc=ChangeIntegrationInstanceStatusUseCase(connection),
        set_integration_instance_credential_uc=SetIntegrationInstanceCredentialUseCase(connection, secret_store),
        create_webhook_endpoint_uc=CreateWebhookEndpointUseCase(connection),
        change_webhook_endpoint_status_uc=ChangeWebhookEndpointStatusUseCase(connection),
        record_integration_health_check_uc=RecordIntegrationHealthCheckUseCase(connection),
        create_notification_account_uc=CreateNotificationAccountUseCase(connection),
        update_notification_account_uc=UpdateNotificationAccountUseCase(connection),
        change_notification_account_status_uc=ChangeNotificationAccountStatusUseCase(connection),
        create_notification_template_uc=CreateNotificationTemplateUseCase(connection),
        update_notification_template_uc=UpdateNotificationTemplateUseCase(connection),
        change_notification_template_status_uc=ChangeNotificationTemplateStatusUseCase(connection),
        create_notification_route_uc=CreateNotificationRouteUseCase(connection),
        change_notification_route_status_uc=ChangeNotificationRouteStatusUseCase(connection),
        create_feature_flag_uc=CreateFeatureFlagUseCase(connection),
        update_feature_flag_uc=UpdateFeatureFlagUseCase(connection),
        change_feature_flag_status_uc=ChangeFeatureFlagStatusUseCase(connection),
        request_feature_flag_change_uc=RequestFeatureFlagChangeUseCase(connection),
        create_theme_uc=CreateThemeUseCase(connection),
        update_theme_uc=UpdateThemeUseCase(connection),
        change_theme_status_uc=ChangeThemeStatusUseCase(connection),
        create_design_token_uc=CreateDesignTokenUseCase(connection),
        update_design_token_uc=UpdateDesignTokenUseCase(connection),
        create_density_profile_uc=CreateDensityProfileUseCase(connection),
        update_density_profile_uc=UpdateDensityProfileUseCase(connection),
        change_density_profile_status_uc=ChangeDensityProfileStatusUseCase(connection),
        create_appearance_preference_uc=CreateAppearancePreferenceUseCase(connection),
        change_appearance_preference_status_uc=ChangeAppearancePreferenceStatusUseCase(connection),
        create_cache_expiration_policy_uc=CreateCacheExpirationPolicyUseCase(connection),
        update_cache_expiration_policy_uc=UpdateCacheExpirationPolicyUseCase(connection),
        change_cache_expiration_policy_status_uc=ChangeCacheExpirationPolicyStatusUseCase(connection),
        user_management_service=user_management_service,
        role_management_service=role_management_service,
        user_security_service=user_security_service,
        permission_query_service=permission_query_service,
        save_user_uc=SaveUserUseCase(user_management_service),
        set_user_active_uc=SetUserActiveUseCase(user_management_service),
        save_role_uc=SaveRoleUseCase(role_management_service),
        company_profile_service=company_profile_service,
        set_installation_branch_uc=SetInstallationBranchUseCase(company_profile_service),
    )

    def has_permission(permission: str) -> bool:
        return verificar_permiso(container, permission, mostrar_alerta=False)

    pending_flag_requests = len(presenter.list_pending_feature_flag_change_requests())
    badges = {"pending_flag_requests": pending_flag_requests} if pending_flag_requests else {}

    return ConfiguracionView(presenter, has_permission=has_permission, badges=badges, parent=parent)
