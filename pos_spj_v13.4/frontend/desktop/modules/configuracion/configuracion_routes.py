"""Canonical route registry for the Configuración internal sidebar.
Mirrors `frontend/desktop/modules/transfers/transfers_routes.py`.
"""
from __future__ import annotations

from backend.application.configuracion.permissions import ConfiguracionPermissions

from .navigation.configuracion_sidebar import CONFIGURACION_NAV

CONFIGURACION_ROUTE_IDS = frozenset(entry.page_id for entry in CONFIGURACION_NAV)


def build_page(page_id: str, presenter):
    """Build one canonical page; unknown route IDs are rejected."""
    if page_id not in CONFIGURACION_ROUTE_IDS:
        raise KeyError(f"Unknown Configuración route: {page_id}")
    from .pages import PAGE_CLASSES
    return PAGE_CLASSES[page_id](presenter)


def build_configuracion_view(*, connection, session_context, parent=None):
    """La ÚNICA composición de Configuración: la usan la shell viva
    (`ConfiguracionModuleActivator`) y las pruebas.

    Hasta 2026-10-04 había dos composiciones con las mismas 84 dependencias.
    Sólo la de las pruebas pasaba `has_permission` a la vista, así que la
    shell viva mostraba las once secciones a cualquiera que abriera el
    módulo (un usuario `solo_lectura` veía usuarios y auditoría) mientras
    todas las pruebas pasaban. Una sola función cierra esa deriva.
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
        SetDeviceWindowsPrinterUseCase,
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
        ImportDisplayMediaUseCase,
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
        TestIntegrationConnectionUseCase,
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
    from backend.application.use_cases.save_role_permissions_use_case import (
        SaveRolePermissionsUseCase,
    )
    from backend.application.security.role_permission_matrix import RolePermissionMatrixQuery
    from backend.application.security.user_permission_matrix import UserPermissionMatrixQuery
    from backend.application.use_cases.save_user_permissions_use_case import (
        SaveUserPermissionsUseCase,
    )
    from backend.application.use_cases.configuracion.device_test_use_cases import TestDeviceUseCase
    from backend.application.use_cases.set_installation_branch_use_case import (
        SetInstallationBranchUseCase,
    )
    from backend.application.organization.org_structure_service import OrgStructureService
    from backend.application.security.role_assignment_service import RoleAssignmentService
    from backend.application.configuracion.settings_services import (
        CompanyProfileService,
        RoleManagementService,
        UserManagementService,
    )
    from backend.infrastructure.db.repositories.settings.audit_log_repository import (
        SqliteAuditLogRepository,
    )
    from backend.infrastructure.db.repositories.security.grant_version_repository import (
        SqliteGrantVersionRepository,
    )
    from backend.infrastructure.db.repositories.settings.installation_branch_repository import (
        SqliteInstallationBranchRepository,
    )
    from backend.infrastructure.db.repositories.settings.user_directory_repository import (
        SqliteUserDirectoryRepository,
    )
    from backend.application.services.user_security_service import UserSecurityService
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
        ConfiguracionActionAuthorizer,
        ConfiguracionAuthorizationPolicy,
        SessionPermissionChecker,
    )
    from backend.infrastructure.db.repositories.settings.configuracion_security_repositories import (
        ConfiguracionAuditLogRepository,
    )
    from frontend.desktop.modules.configuracion.configuracion_presenter import ConfiguracionPresenter
    from frontend.desktop.modules.configuracion.software_updates_presenter import (
        SoftwareUpdatesPresenter,
    )
    from backend.infrastructure.desktop.software_updates_factory import (
        build_software_update_dependencies,
        copy_package_file,
    )
    from frontend.desktop.shell.application_lifecycle import request_update_handoff
    from frontend.desktop.modules.configuracion.configuracion_view import ConfiguracionView

    session = session_context
    secret_store = build_default_secret_store()
    query_service = ConfiguracionWorkspaceQueryService(connection, secret_store)
    authorization = ConfiguracionAuthorizationPolicy(SessionPermissionChecker(session))
    # SDLC-ARQ-PERM-001: cada caso de uso verifica su permiso en backend con la
    # MISMA política (y el actor de la sesión, no el que traiga el llamador).
    action_authorizer = ConfiguracionActionAuthorizer(
        authorization, actor=lambda: str(getattr(session, "user_id", "") or ""))
    user_directory = SqliteUserDirectoryRepository(connection)
    audit_log = SqliteAuditLogRepository(connection)
    user_management_service = UserManagementService(
        user_directory, audit_log, grant_versions=SqliteGrantVersionRepository(connection))
    role_management_service = RoleManagementService(user_directory, audit_log)
    company_profile_service = CompanyProfileService(
        SqliteInstallationBranchRepository(connection))
    user_security_service = UserSecurityService(
        connection, permission_checker=session.tiene_permiso if session is not None else None)
    presenter = ConfiguracionPresenter(
        query_service, session_context=session,
        address_search_factory=_address_search_factory(connection),
        authorization=authorization,
        audit_log_repository=ConfiguracionAuditLogRepository(connection),
        approve_change_request_uc=ApproveFeatureFlagChangeRequestUseCase(connection, authorization=action_authorizer),
        reject_change_request_uc=RejectFeatureFlagChangeRequestUseCase(connection, authorization=action_authorizer),
        apply_change_request_uc=ApplyFeatureFlagChangeRequestUseCase(connection, authorization=action_authorizer),
        set_default_theme_uc=SetDefaultThemeUseCase(connection, authorization=action_authorizer),
        register_device_profile_uc=RegisterDeviceProfileUseCase(connection, authorization=action_authorizer),
        register_device_uc=RegisterDeviceUseCase(connection, authorization=action_authorizer),
        update_device_uc=UpdateDeviceUseCase(connection, authorization=action_authorizer),
        change_device_status_uc=ChangeDeviceStatusUseCase(connection, authorization=action_authorizer),
        create_document_template_uc=CreateDocumentTemplateUseCase(connection, authorization=action_authorizer),
        create_next_template_version_uc=CreateNextTemplateVersionUseCase(connection, authorization=action_authorizer),
        change_template_version_status_uc=ChangeTemplateVersionStatusUseCase(connection, authorization=action_authorizer),
        save_company_profile_uc=SaveCompanyProfileUseCase(connection, authorization=action_authorizer),
        register_branch_profile_uc=RegisterBranchProfileUseCase(connection, authorization=action_authorizer),
        update_branch_profile_uc=UpdateBranchProfileUseCase(connection, authorization=action_authorizer),
        register_workstation_uc=RegisterWorkstationUseCase(connection, authorization=action_authorizer),
        update_workstation_uc=UpdateWorkstationUseCase(connection, authorization=action_authorizer),
        change_workstation_status_uc=ChangeWorkstationStatusUseCase(connection, authorization=action_authorizer),
        assign_device_uc=AssignDeviceUseCase(connection, authorization=action_authorizer),
        unassign_device_uc=UnassignDeviceUseCase(connection, authorization=action_authorizer),
        create_print_route_uc=CreatePrintRouteUseCase(connection, authorization=action_authorizer),
        update_print_route_uc=UpdatePrintRouteUseCase(connection, authorization=action_authorizer),
        change_print_route_status_uc=ChangePrintRouteStatusUseCase(connection, authorization=action_authorizer),
        update_document_template_uc=UpdateDocumentTemplateUseCase(connection, authorization=action_authorizer),
        change_document_template_status_uc=ChangeDocumentTemplateStatusUseCase(connection, authorization=action_authorizer),
        create_marketing_campaign_uc=CreateMarketingCampaignUseCase(connection, authorization=action_authorizer),
        update_marketing_campaign_uc=UpdateMarketingCampaignUseCase(connection, authorization=action_authorizer),
        change_marketing_campaign_status_uc=ChangeMarketingCampaignStatusUseCase(connection, authorization=action_authorizer),
        create_content_uc=CreateContentUseCase(connection, authorization=action_authorizer),
        update_content_uc=UpdateContentUseCase(connection, authorization=action_authorizer),
        change_content_status_uc=ChangeContentStatusUseCase(connection, authorization=action_authorizer),
        create_content_campaign_uc=CreateContentCampaignUseCase(connection, authorization=action_authorizer),
        update_content_campaign_uc=UpdateContentCampaignUseCase(connection, authorization=action_authorizer),
        change_content_campaign_status_uc=ChangeContentCampaignStatusUseCase(connection, authorization=action_authorizer),
        create_advertising_slot_uc=CreateAdvertisingSlotUseCase(connection, authorization=action_authorizer),
        update_advertising_slot_uc=UpdateAdvertisingSlotUseCase(connection, authorization=action_authorizer),
        change_advertising_slot_status_uc=ChangeAdvertisingSlotStatusUseCase(connection, authorization=action_authorizer),
        assign_campaign_placement_uc=AssignCampaignPlacementUseCase(connection, authorization=action_authorizer),
        unassign_campaign_placement_uc=UnassignCampaignPlacementUseCase(connection, authorization=action_authorizer),
        create_integration_definition_uc=CreateIntegrationDefinitionUseCase(connection, authorization=action_authorizer),
        update_integration_definition_uc=UpdateIntegrationDefinitionUseCase(connection, authorization=action_authorizer),
        change_integration_definition_status_uc=ChangeIntegrationDefinitionStatusUseCase(connection, authorization=action_authorizer),
        create_integration_instance_uc=CreateIntegrationInstanceUseCase(connection, authorization=action_authorizer),
        update_integration_instance_uc=UpdateIntegrationInstanceUseCase(connection, authorization=action_authorizer),
        change_integration_instance_status_uc=ChangeIntegrationInstanceStatusUseCase(connection, authorization=action_authorizer),
        set_integration_instance_credential_uc=SetIntegrationInstanceCredentialUseCase(connection, secret_store, authorization=action_authorizer),
        create_webhook_endpoint_uc=CreateWebhookEndpointUseCase(connection, authorization=action_authorizer),
        change_webhook_endpoint_status_uc=ChangeWebhookEndpointStatusUseCase(connection, authorization=action_authorizer),
        record_integration_health_check_uc=RecordIntegrationHealthCheckUseCase(connection, authorization=action_authorizer),
        create_notification_account_uc=CreateNotificationAccountUseCase(connection, authorization=action_authorizer),
        update_notification_account_uc=UpdateNotificationAccountUseCase(connection, authorization=action_authorizer),
        change_notification_account_status_uc=ChangeNotificationAccountStatusUseCase(connection, authorization=action_authorizer),
        create_notification_template_uc=CreateNotificationTemplateUseCase(connection, authorization=action_authorizer),
        update_notification_template_uc=UpdateNotificationTemplateUseCase(connection, authorization=action_authorizer),
        change_notification_template_status_uc=ChangeNotificationTemplateStatusUseCase(connection, authorization=action_authorizer),
        create_notification_route_uc=CreateNotificationRouteUseCase(connection, authorization=action_authorizer),
        change_notification_route_status_uc=ChangeNotificationRouteStatusUseCase(connection, authorization=action_authorizer),
        create_feature_flag_uc=CreateFeatureFlagUseCase(connection, authorization=action_authorizer),
        update_feature_flag_uc=UpdateFeatureFlagUseCase(connection, authorization=action_authorizer),
        change_feature_flag_status_uc=ChangeFeatureFlagStatusUseCase(connection, authorization=action_authorizer),
        request_feature_flag_change_uc=RequestFeatureFlagChangeUseCase(connection, authorization=action_authorizer),
        create_theme_uc=CreateThemeUseCase(connection, authorization=action_authorizer),
        update_theme_uc=UpdateThemeUseCase(connection, authorization=action_authorizer),
        change_theme_status_uc=ChangeThemeStatusUseCase(connection, authorization=action_authorizer),
        create_design_token_uc=CreateDesignTokenUseCase(connection, authorization=action_authorizer),
        update_design_token_uc=UpdateDesignTokenUseCase(connection, authorization=action_authorizer),
        create_density_profile_uc=CreateDensityProfileUseCase(connection, authorization=action_authorizer),
        update_density_profile_uc=UpdateDensityProfileUseCase(connection, authorization=action_authorizer),
        change_density_profile_status_uc=ChangeDensityProfileStatusUseCase(connection, authorization=action_authorizer),
        create_appearance_preference_uc=CreateAppearancePreferenceUseCase(connection, authorization=action_authorizer),
        change_appearance_preference_status_uc=ChangeAppearancePreferenceStatusUseCase(connection, authorization=action_authorizer),
        create_cache_expiration_policy_uc=CreateCacheExpirationPolicyUseCase(connection, authorization=action_authorizer),
        update_cache_expiration_policy_uc=UpdateCacheExpirationPolicyUseCase(connection, authorization=action_authorizer),
        change_cache_expiration_policy_status_uc=ChangeCacheExpirationPolicyStatusUseCase(connection, authorization=action_authorizer),
        user_management_service=user_management_service,
        role_management_service=role_management_service,
        user_security_service=user_security_service,
        save_user_uc=SaveUserUseCase(user_management_service, authorization=authorization),
        set_user_active_uc=SetUserActiveUseCase(user_management_service, authorization=authorization),
        save_role_uc=SaveRoleUseCase(role_management_service, authorization=authorization),
        company_profile_service=company_profile_service,
        set_installation_branch_uc=SetInstallationBranchUseCase(
            company_profile_service, authorization=action_authorizer),
        role_permission_matrix_query=RolePermissionMatrixQuery(connection),
        save_role_permissions_uc=SaveRolePermissionsUseCase(connection, authorization=authorization),
        test_integration_connection_uc=TestIntegrationConnectionUseCase(connection, secret_store, authorization=action_authorizer),
        test_device_uc=TestDeviceUseCase(connection, authorization=action_authorizer),
        user_permission_matrix_query=UserPermissionMatrixQuery(connection),
        save_user_permissions_uc=SaveUserPermissionsUseCase(connection, authorization=authorization),
        import_display_media_uc=ImportDisplayMediaUseCase(connection, authorization=action_authorizer),
        set_device_windows_printer_uc=SetDeviceWindowsPrinterUseCase(connection, authorization=action_authorizer),
        ticket_designer=_ticket_designer(connection, action_authorizer),
        org_structure=OrgStructureService(
            connection, authorization=authorization,
            actor=lambda: getattr(session, "user_id", "") or "", audit_log=audit_log),
        role_assignments=RoleAssignmentService(
            connection, authorization=authorization,
            actor=lambda: getattr(session, "user_id", "") or "", audit_log=audit_log,
            grant_versions=SqliteGrantVersionRepository(connection)),
        software_updates=SoftwareUpdatesPresenter(
            build_software_update_dependencies(connection, session_context=session),
            copy_file=copy_package_file, request_handoff=request_update_handoff),
    )

    def has_permission(permission: str) -> bool:
        """Comprobación para OCULTAR opciones del menú, no para autorizar.

        Usa la MISMA política que ya valida las operaciones (`authorization`,
        construida arriba con el verificador de la sesión viva), no un camino
        paralelo: dos formas distintas de responder "¿puede?" acaban
        divergiendo, y entonces la interfaz muestra un botón que la operación
        va a rechazar.

        `has_permission` no lanza — devuelve False. Es lo correcto para pintar
        una pantalla: quedarse sin una opción no es un error, y quien sí
        autoriza de verdad es `require()` en cada caso de uso.
        """
        return authorization.has_permission(
            getattr(session, "user_id", "") or "", permission)

    # La insignia de Feature Flags sólo se calcula para quien puede ver esa
    # sección: el conteo también es información de la sección.
    pending_flag_requests = (
        len(presenter.list_pending_feature_flag_change_requests())
        if has_permission(ConfiguracionPermissions.FEATURE_FLAGS_VIEW) else 0)
    badges = {"pending_flag_requests": pending_flag_requests} if pending_flag_requests else {}

    return ConfiguracionView(presenter, has_permission=has_permission, badges=badges, parent=parent)


def _address_search_factory(connection):
    """El servicio estándar de direcciones, leído de Integraciones cada vez que
    se abre un diálogo: así un token de Mapbox recién guardado se usa sin
    reiniciar la aplicación."""
    def _build():
        from backend.infrastructure.maps.address_search_factory import (
            build_address_search_service,
        )
        return build_address_search_service(connection)
    return _build


def _ticket_designer(connection, authorization):
    """Diseñador de tickets y logos (comparativa de tickets, 2026-10-16)."""
    from backend.application.use_cases.configuracion.ticket_designer_service import (
        TicketDesignerService,
    )
    return TicketDesignerService(connection, authorization=authorization)
