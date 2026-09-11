"""Presentation orchestration; business rules stay in the domain/use
cases. Mirrors `frontend/desktop/modules/transfers/transfers_presenter.py`'s
shape: identity is never fabricated — without a valid session the actor
is empty and the use case's own fail-closed checks (or this presenter's
own guard) refuse the mutation downstream.
"""
from __future__ import annotations

import json
import logging

from backend.application.configuracion.permissions import ConfiguracionPermissions
from backend.application.use_cases.configuracion.device_management_use_cases import DeviceStatusAction
from backend.application.use_cases.configuracion.document_template_use_cases import (
    DocumentTemplateStatusAction,
    TemplateVersionAction,
)
from backend.application.use_cases.configuracion.workstation_use_cases import WorkstationStatusAction
from backend.application.use_cases.configuracion.print_route_use_cases import PrintRouteStatusAction
from backend.application.use_cases.configuracion.marketing_campaign_use_cases import (
    MarketingCampaignStatusAction,
)
from backend.application.use_cases.configuracion.customer_display_advertising_use_cases import (
    AdvertisingSlotStatusAction,
    ContentCampaignStatusAction,
    ContentStatusAction,
)
from backend.application.use_cases.configuracion.integration_management_use_cases import (
    IntegrationDefinitionStatusAction,
    IntegrationInstanceStatusAction,
    WebhookEndpointStatusAction,
)
from backend.application.use_cases.configuracion.notification_management_use_cases import (
    NotificationAccountStatusAction,
    NotificationRouteStatusAction,
    NotificationTemplateStatusAction,
)
from backend.application.use_cases.configuracion.feature_flag_management_use_cases import (
    FeatureFlagStatusAction,
)
from backend.application.use_cases.configuracion.appearance_management_use_cases import (
    AppearancePreferenceStatusAction,
    DensityProfileStatusAction,
    ThemeStatusAction,
)
from backend.application.use_cases.configuracion.offline_management_use_cases import (
    CacheExpirationPolicyStatusAction,
)
from backend.application.commands.settings_commands import (
    SaveRoleCommand,
    SaveUserCommand,
    SetInstallationBranchCommand,
    SetUserActiveCommand,
)
from backend.domain.appearance.exceptions import AppearanceDomainError
from backend.domain.customer_display.exceptions import CustomerDisplayDomainError
from backend.domain.device_management.exceptions import DeviceManagementDomainError
from backend.domain.integrations.exceptions import IntegrationsDomainError
from backend.domain.notifications.exceptions import NotificationsDomainError
from backend.domain.offline.exceptions import OfflineDomainError
from backend.domain.document_output.exceptions import DocumentOutputDomainError
from backend.domain.feature_flags.exceptions import FeatureFlagsDomainError
from backend.domain.settings.exceptions import (
    ConfigurationDomainError,
    ConfigurationPermissionDeniedError,
)
from backend.security.audit.sensitive_data_redaction import redact_mapping
from backend.shared.ids import new_uuid

try:
    import bcrypt as _bcrypt
except ImportError:
    _bcrypt = None

logger = logging.getLogger("spj.configuracion.presenter")

# SET-1: permission code required for each mutating command whose gate
# doesn't depend on the requested action (device/template status changes
# resolve their code dynamically — see _DEVICE_STATUS_PERMISSIONS /
# _TEMPLATE_STATUS_PERMISSIONS below).
_DEVICE_STATUS_PERMISSIONS = {
    DeviceStatusAction.ACTIVATE: ConfiguracionPermissions.DISPOSITIVOS_EDITAR,
    DeviceStatusAction.DEACTIVATE: ConfiguracionPermissions.DISPOSITIVOS_EDITAR,
    DeviceStatusAction.UNBLOCK: ConfiguracionPermissions.DISPOSITIVOS_EDITAR,
    DeviceStatusAction.BLOCK: ConfiguracionPermissions.DISPOSITIVOS_DESHABILITAR,
    DeviceStatusAction.RETIRE: ConfiguracionPermissions.DISPOSITIVOS_DESHABILITAR,
}
_TEMPLATE_STATUS_PERMISSIONS = {
    TemplateVersionAction.SUBMIT_FOR_APPROVAL: ConfiguracionPermissions.DOCUMENTOS_PLANTILLA_EDITAR,
    TemplateVersionAction.REJECT: ConfiguracionPermissions.DOCUMENTOS_PLANTILLA_APROBAR,
    TemplateVersionAction.APPROVE: ConfiguracionPermissions.DOCUMENTOS_PLANTILLA_APROBAR,
    TemplateVersionAction.ACTIVATE: ConfiguracionPermissions.DOCUMENTOS_PLANTILLA_ACTIVAR,
    TemplateVersionAction.DEACTIVATE: ConfiguracionPermissions.DOCUMENTOS_PLANTILLA_EDITAR,
    TemplateVersionAction.EXPIRE: ConfiguracionPermissions.DOCUMENTOS_PLANTILLA_EDITAR,
    TemplateVersionAction.ARCHIVE: ConfiguracionPermissions.DOCUMENTOS_PLANTILLA_EDITAR,
}
# Status changes worth a persisted before/after audit entry (§60): the
# ones that gate/unblock a device or move a document towards production
# use. Routine edits (rename, notes) are permission-gated but not
# audit-logged — same scope boundary the plan's own audit checklist draws.
_DEVICE_STATUS_AUDITED = {DeviceStatusAction.BLOCK, DeviceStatusAction.RETIRE}
_TEMPLATE_STATUS_AUDITED = {TemplateVersionAction.APPROVE, TemplateVersionAction.ACTIVATE}
_WORKSTATION_STATUS_PERMISSIONS = {
    WorkstationStatusAction.ACTIVATE: ConfiguracionPermissions.ESTACION_EDITAR,
    WorkstationStatusAction.DEACTIVATE: ConfiguracionPermissions.ESTACION_EDITAR,
    WorkstationStatusAction.ENTER_MAINTENANCE: ConfiguracionPermissions.ESTACION_EDITAR,
    WorkstationStatusAction.EXIT_MAINTENANCE: ConfiguracionPermissions.ESTACION_EDITAR,
    WorkstationStatusAction.UNBLOCK: ConfiguracionPermissions.ESTACION_EDITAR,
    WorkstationStatusAction.BLOCK: ConfiguracionPermissions.ESTACION_BLOQUEAR,
    WorkstationStatusAction.RETIRE: ConfiguracionPermissions.ESTACION_RETIRAR,
}
_WORKSTATION_STATUS_AUDITED = {WorkstationStatusAction.BLOCK, WorkstationStatusAction.RETIRE}
# SET-11 follow-up: the whole template *family*'s active/inactive
# toggle (DocumentTemplateStatusAction) is a different action from a
# single version's status (TemplateVersionAction above) — retiring a
# template entirely is always audited, same weight as blocking a device.
_DOCUMENT_TEMPLATE_STATUS_PERMISSION = ConfiguracionPermissions.DOCUMENTOS_PLANTILLA_ACTIVAR
# SET-13 cutover: same weight as the template family toggle above — a
# campaign starting/stopping to print on live tickets is a critical
# transition, always audited; create/edit are routine content edits.
_CAMPAIGN_STATUS_PERMISSION = ConfiguracionPermissions.DOCUMENTOS_CAMPANA_ACTIVAR
# SET-18 cutover: ContentCampaign's 7-state machine mirrors
# DocumentTemplateVersion's exact shape (SET-11) — same permission-mapping
# discipline as _TEMPLATE_STATUS_PERMISSIONS. SUBMIT/ACTIVATE/DEACTIVATE/
# EXPIRE/ARCHIVE are "programar" (schedule/lifecycle management);
# APPROVE/REJECT are the actual approval-workflow gate.
_CONTENT_CAMPAIGN_STATUS_PERMISSIONS = {
    ContentCampaignStatusAction.SUBMIT_FOR_APPROVAL: ConfiguracionPermissions.PANTALLA_CLIENTE_CAMPANA_PROGRAMAR,
    ContentCampaignStatusAction.REJECT: ConfiguracionPermissions.PANTALLA_CLIENTE_CONTENIDO_APROBAR,
    ContentCampaignStatusAction.APPROVE: ConfiguracionPermissions.PANTALLA_CLIENTE_CONTENIDO_APROBAR,
    ContentCampaignStatusAction.ACTIVATE: ConfiguracionPermissions.PANTALLA_CLIENTE_CAMPANA_PROGRAMAR,
    ContentCampaignStatusAction.DEACTIVATE: ConfiguracionPermissions.PANTALLA_CLIENTE_CAMPANA_PROGRAMAR,
    ContentCampaignStatusAction.EXPIRE: ConfiguracionPermissions.PANTALLA_CLIENTE_CAMPANA_PROGRAMAR,
    ContentCampaignStatusAction.ARCHIVE: ConfiguracionPermissions.PANTALLA_CLIENTE_CAMPANA_PROGRAMAR,
}
_CONTENT_CAMPAIGN_STATUS_AUDITED = {ContentCampaignStatusAction.APPROVE, ContentCampaignStatusAction.ACTIVATE}


def _to_json(value) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)


class ConfiguracionPresenter:
    def __init__(
        self, query_service, *, session_context=None, approve_change_request_uc=None,
        reject_change_request_uc=None, apply_change_request_uc=None, set_default_theme_uc=None,
        register_device_profile_uc=None, register_device_uc=None, update_device_uc=None,
        change_device_status_uc=None, create_document_template_uc=None,
        create_next_template_version_uc=None, change_template_version_status_uc=None,
        save_company_profile_uc=None, register_branch_profile_uc=None, update_branch_profile_uc=None,
        register_workstation_uc=None, update_workstation_uc=None, change_workstation_status_uc=None,
        assign_device_uc=None, unassign_device_uc=None,
        create_print_route_uc=None, update_print_route_uc=None, change_print_route_status_uc=None,
        update_document_template_uc=None, change_document_template_status_uc=None,
        create_marketing_campaign_uc=None, update_marketing_campaign_uc=None,
        change_marketing_campaign_status_uc=None,
        create_content_uc=None, update_content_uc=None, change_content_status_uc=None,
        create_content_campaign_uc=None, update_content_campaign_uc=None,
        change_content_campaign_status_uc=None,
        create_advertising_slot_uc=None, update_advertising_slot_uc=None,
        change_advertising_slot_status_uc=None,
        assign_campaign_placement_uc=None, unassign_campaign_placement_uc=None,
        create_integration_definition_uc=None, update_integration_definition_uc=None,
        change_integration_definition_status_uc=None,
        create_integration_instance_uc=None, update_integration_instance_uc=None,
        change_integration_instance_status_uc=None, set_integration_instance_credential_uc=None,
        create_webhook_endpoint_uc=None, change_webhook_endpoint_status_uc=None,
        record_integration_health_check_uc=None,
        create_notification_account_uc=None, update_notification_account_uc=None,
        change_notification_account_status_uc=None,
        create_notification_template_uc=None, update_notification_template_uc=None,
        change_notification_template_status_uc=None,
        create_notification_route_uc=None, change_notification_route_status_uc=None,
        create_feature_flag_uc=None, update_feature_flag_uc=None, change_feature_flag_status_uc=None,
        request_feature_flag_change_uc=None,
        create_theme_uc=None, update_theme_uc=None, change_theme_status_uc=None,
        create_design_token_uc=None, update_design_token_uc=None,
        create_density_profile_uc=None, update_density_profile_uc=None,
        change_density_profile_status_uc=None,
        create_appearance_preference_uc=None, change_appearance_preference_status_uc=None,
        create_cache_expiration_policy_uc=None, update_cache_expiration_policy_uc=None,
        change_cache_expiration_policy_status_uc=None,
        user_management_service=None, role_management_service=None,
        user_security_service=None,
        save_user_uc=None, set_user_active_uc=None, save_role_uc=None,
        company_profile_service=None, set_installation_branch_uc=None,
        authorization=None, audit_log_repository=None,
    ) -> None:
        self._query_service = query_service
        self._session = session_context
        self._approve_uc = approve_change_request_uc
        self._reject_uc = reject_change_request_uc
        self._apply_uc = apply_change_request_uc
        self._set_default_theme_uc = set_default_theme_uc
        self._register_device_profile_uc = register_device_profile_uc
        self._register_device_uc = register_device_uc
        self._update_device_uc = update_device_uc
        self._change_device_status_uc = change_device_status_uc
        self._create_document_template_uc = create_document_template_uc
        self._create_next_template_version_uc = create_next_template_version_uc
        self._change_template_version_status_uc = change_template_version_status_uc
        self._save_company_profile_uc = save_company_profile_uc
        self._register_branch_profile_uc = register_branch_profile_uc
        self._update_branch_profile_uc = update_branch_profile_uc
        self._register_workstation_uc = register_workstation_uc
        self._update_workstation_uc = update_workstation_uc
        self._change_workstation_status_uc = change_workstation_status_uc
        self._assign_device_uc = assign_device_uc
        self._unassign_device_uc = unassign_device_uc
        self._create_print_route_uc = create_print_route_uc
        self._update_print_route_uc = update_print_route_uc
        self._change_print_route_status_uc = change_print_route_status_uc
        self._update_document_template_uc = update_document_template_uc
        self._change_document_template_status_uc = change_document_template_status_uc
        self._create_marketing_campaign_uc = create_marketing_campaign_uc
        self._update_marketing_campaign_uc = update_marketing_campaign_uc
        self._change_marketing_campaign_status_uc = change_marketing_campaign_status_uc
        self._create_content_uc = create_content_uc
        self._update_content_uc = update_content_uc
        self._change_content_status_uc = change_content_status_uc
        self._create_content_campaign_uc = create_content_campaign_uc
        self._update_content_campaign_uc = update_content_campaign_uc
        self._change_content_campaign_status_uc = change_content_campaign_status_uc
        self._create_advertising_slot_uc = create_advertising_slot_uc
        self._update_advertising_slot_uc = update_advertising_slot_uc
        self._change_advertising_slot_status_uc = change_advertising_slot_status_uc
        self._assign_campaign_placement_uc = assign_campaign_placement_uc
        self._unassign_campaign_placement_uc = unassign_campaign_placement_uc
        self._create_integration_definition_uc = create_integration_definition_uc
        self._update_integration_definition_uc = update_integration_definition_uc
        self._change_integration_definition_status_uc = change_integration_definition_status_uc
        self._create_integration_instance_uc = create_integration_instance_uc
        self._update_integration_instance_uc = update_integration_instance_uc
        self._change_integration_instance_status_uc = change_integration_instance_status_uc
        self._set_integration_instance_credential_uc = set_integration_instance_credential_uc
        self._create_webhook_endpoint_uc = create_webhook_endpoint_uc
        self._change_webhook_endpoint_status_uc = change_webhook_endpoint_status_uc
        self._record_integration_health_check_uc = record_integration_health_check_uc
        self._create_notification_account_uc = create_notification_account_uc
        self._update_notification_account_uc = update_notification_account_uc
        self._change_notification_account_status_uc = change_notification_account_status_uc
        self._create_notification_template_uc = create_notification_template_uc
        self._update_notification_template_uc = update_notification_template_uc
        self._change_notification_template_status_uc = change_notification_template_status_uc
        self._create_notification_route_uc = create_notification_route_uc
        self._change_notification_route_status_uc = change_notification_route_status_uc
        self._create_feature_flag_uc = create_feature_flag_uc
        self._update_feature_flag_uc = update_feature_flag_uc
        self._change_feature_flag_status_uc = change_feature_flag_status_uc
        self._request_feature_flag_change_uc = request_feature_flag_change_uc
        self._create_theme_uc = create_theme_uc
        self._update_theme_uc = update_theme_uc
        self._change_theme_status_uc = change_theme_status_uc
        self._create_design_token_uc = create_design_token_uc
        self._update_design_token_uc = update_design_token_uc
        self._create_density_profile_uc = create_density_profile_uc
        self._update_density_profile_uc = update_density_profile_uc
        self._change_density_profile_status_uc = change_density_profile_status_uc
        self._create_appearance_preference_uc = create_appearance_preference_uc
        self._change_appearance_preference_status_uc = change_appearance_preference_status_uc
        self._create_cache_expiration_policy_uc = create_cache_expiration_policy_uc
        self._update_cache_expiration_policy_uc = update_cache_expiration_policy_uc
        self._change_cache_expiration_policy_status_uc = change_cache_expiration_policy_status_uc
        self._user_management_service = user_management_service
        self._role_management_service = role_management_service
        self._user_security_service = user_security_service
        self._save_user_uc = save_user_uc
        self._set_user_active_uc = set_user_active_uc
        self._save_role_uc = save_role_uc
        self._company_profile_service = company_profile_service
        self._set_installation_branch_uc = set_installation_branch_uc
        # SET-1: optional — a presenter built without `authorization` skips
        # enforcement entirely (existing tests / isolated call sites keep
        # working unchanged). The live app (configuracion_routes.py) always
        # wires a real ConfiguracionAuthorizationPolicy.
        self._authorization = authorization
        self._audit_log = audit_log_repository

    # authorization / audit -----------------------------------------------------
    def _authorize(self, permission_code: str) -> str | None:
        """Returns an error message if the actor lacks `permission_code`,
        else None. No-op when no policy is wired (see __init__ note)."""
        if self._authorization is None:
            return None
        try:
            self._authorization.require(self._actor(), permission_code)
            return None
        except ConfigurationPermissionDeniedError as exc:
            return str(exc)

    def _record_audit(
        self, *, entity_type: str, entity_id: str, action: str,
        before: dict | None = None, after: dict | None = None, reason: str = "",
    ) -> None:
        if self._audit_log is None:
            return
        try:
            self._audit_log.record(
                entity_type=entity_type, entity_id=entity_id, action=action,
                user_id=self._actor() or None, operation_id=new_uuid(),
                before_json=_to_json(redact_mapping(before)) if before is not None else None,
                after_json=_to_json(redact_mapping(after)) if after is not None else None,
                reason=reason or None,
            )
        except Exception:
            logger.exception("ConfiguracionPresenter._record_audit failed (entity=%s/%s)",
                              entity_type, entity_id)

    def load_page(self, page_id: str, search: str = ""):
        return self._query_service.page(page_id=page_id, search=search)

    def list_pending_feature_flag_change_requests(self):
        return self._query_service.list_pending_feature_flag_change_requests()

    def list_feature_flags(self):
        return self._query_service.list_feature_flags()

    def list_feature_flag_rules(self, flag_id: str):
        return self._query_service.list_feature_flag_rules(flag_id)

    def list_design_tokens_for_theme(self, theme_id: str):
        return self._query_service.list_design_tokens_for_theme(theme_id)

    def list_density_profiles(self):
        return self._query_service.list_density_profiles()

    def list_appearance_preferences(self):
        return self._query_service.list_appearance_preferences()

    def list_cache_expiration_policies(self):
        return self._query_service.list_cache_expiration_policies()

    def list_offline_cache_entries(self):
        return self._query_service.list_offline_cache_entries()

    def list_users(self):
        return self._query_service.list_users()

    def get_user_form_data(self, user_id: str):
        return self._query_service.get_user_form_data(user_id)

    def list_roles(self):
        return self._query_service.list_roles()

    def list_role_names(self):
        return self._query_service.list_role_names()

    def list_branches_for_user_selector(self):
        return self._query_service.list_branches_for_user_selector()

    def list_employees_for_user_selector(self):
        return self._query_service.list_employees_for_user_selector()

    def audit_log_rows(self, limit: int = 200):
        return self._query_service.audit_log_rows(limit)

    def list_themes(self):
        return self._query_service.list_themes()

    def list_device_profiles(self):
        return self._query_service.list_device_profiles()

    def list_branches(self):
        return self._query_service.list_branches()

    def get_device(self, device_id: str):
        return self._query_service.get_device(device_id)

    def get_template(self, template_id: str):
        return self._query_service.get_template(template_id)

    def list_template_versions(self, template_id: str):
        return self._query_service.list_template_versions(template_id)

    def get_company_profile(self):
        return self._query_service.get_company_profile()

    def get_branch_profile(self, branch_id: str):
        return self._query_service.get_branch_profile(branch_id)

    def list_unregistered_branches(self):
        return self._query_service.list_unregistered_branches()

    def get_installation_branch(self):
        return self._query_service.get_installation_branch()

    def get_workstation(self, workstation_id: str):
        return self._query_service.get_workstation(workstation_id)

    def list_devices(self):
        return self._query_service.list_devices()

    def list_workstation_assignments(self, workstation_id: str):
        return self._query_service.list_workstation_assignments(workstation_id)

    def list_print_routes(self):
        return self._query_service.list_print_routes()

    def list_marketing_campaigns(self):
        return self._query_service.list_marketing_campaigns()

    def get_display_content(self, content_id: str):
        return self._query_service.get_display_content(content_id)

    def list_display_content(self):
        return self._query_service.list_display_content()

    def list_content_campaigns(self):
        return self._query_service.list_content_campaigns()

    def list_advertising_slots(self):
        return self._query_service.list_advertising_slots()

    def list_campaign_placements(self):
        return self._query_service.list_campaign_placements()

    def get_impression_summary(self, placement_id: str) -> str:
        return self._query_service.get_impression_summary(placement_id)

    def list_integration_definitions(self):
        return self._query_service.list_integration_definitions()

    def list_integration_instances(self, definition_id: str):
        return self._query_service.list_integration_instances(definition_id)

    def list_webhook_endpoints(self, instance_id: str):
        return self._query_service.list_webhook_endpoints(instance_id)

    def list_integration_health_checks(self, instance_id: str):
        return self._query_service.list_integration_health_checks(instance_id)

    def get_integration_health_status(self, instance_id: str) -> str:
        return self._query_service.get_integration_health_status(instance_id)

    def get_credential_status(self, credential_reference: str | None) -> str:
        return self._query_service.get_credential_status(credential_reference)

    def list_notification_accounts(self):
        return self._query_service.list_notification_accounts()

    def list_notification_templates(self):
        return self._query_service.list_notification_templates()

    def list_notification_routes(self):
        return self._query_service.list_notification_routes()

    # session -----------------------------------------------------------------
    def _actor(self) -> str:
        return str(getattr(self._session, "user_id", None) or "")

    # commands ------------------------------------------------------------------
    def approve_feature_flag_change_request(self, request_id: str) -> tuple[bool, str]:
        if self._approve_uc is None:
            return False, "Aprobación de solicitudes no disponible."
        actor = self._actor()
        if not actor:
            return False, "Sesión inválida; no se puede aprobar sin un usuario autenticado."
        denial = self._authorize(ConfiguracionPermissions.FEATURE_FLAGS_APROBAR)
        if denial:
            return False, denial
        try:
            self._approve_uc.execute(request_id=request_id, approver_user_id=actor)
            return True, "Solicitud aprobada."
        except FeatureFlagsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.approve_feature_flag_change_request failed")
            return False, "Error inesperado; revise el log."

    def reject_feature_flag_change_request(self, request_id: str, reason: str) -> tuple[bool, str]:
        if self._reject_uc is None:
            return False, "Rechazo de solicitudes no disponible."
        reason = (reason or "").strip()
        if not reason:
            return False, "Captura un motivo de rechazo."
        denial = self._authorize(ConfiguracionPermissions.FEATURE_FLAGS_APROBAR)
        if denial:
            return False, denial
        try:
            self._reject_uc.execute(request_id=request_id, reason=reason)
            return True, "Solicitud rechazada."
        except FeatureFlagsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.reject_feature_flag_change_request failed")
            return False, "Error inesperado; revise el log."

    def apply_feature_flag_change_request(self, request_id: str) -> tuple[bool, str]:
        if self._apply_uc is None:
            return False, "Aplicación de solicitudes no disponible."
        denial = self._authorize(ConfiguracionPermissions.FEATURE_FLAGS_ACTIVAR)
        if denial:
            return False, denial
        try:
            rule = self._apply_uc.execute(request_id=request_id)
            return True, f"Solicitud aplicada; regla {rule.id} activa."
        except FeatureFlagsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.apply_feature_flag_change_request failed")
            return False, "Error inesperado; revise el log."

    def create_feature_flag(self, **kwargs) -> tuple[bool, str]:
        if self._create_feature_flag_uc is None:
            return False, "Feature flags no disponibles."
        denial = self._authorize(ConfiguracionPermissions.FEATURE_FLAGS_CREAR)
        if denial:
            return False, denial
        try:
            flag = self._create_feature_flag_uc.execute(**kwargs)
            return True, f"Flag «{flag.code}» creado."
        except FeatureFlagsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.create_feature_flag failed")
            return False, "Error inesperado; revise el log."

    def update_feature_flag(self, **kwargs) -> tuple[bool, str]:
        if self._update_feature_flag_uc is None:
            return False, "Feature flags no disponibles."
        denial = self._authorize(ConfiguracionPermissions.FEATURE_FLAGS_EDITAR)
        if denial:
            return False, denial
        try:
            flag = self._update_feature_flag_uc.execute(**kwargs)
            return True, f"Flag «{flag.code}» actualizado."
        except FeatureFlagsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.update_feature_flag failed")
            return False, "Error inesperado; revise el log."

    def change_feature_flag_status(self, *, flag_id: str, action: str) -> tuple[bool, str]:
        if self._change_feature_flag_status_uc is None:
            return False, "Cambio de estado no disponible."
        try:
            action_enum = FeatureFlagStatusAction(action)
        except ValueError:
            return False, f"Acción de flag desconocida: {action}"
        denial = self._authorize(ConfiguracionPermissions.FEATURE_FLAGS_EDITAR)
        if denial:
            return False, denial
        try:
            flag = self._change_feature_flag_status_uc.execute(flag_id=flag_id, action=action_enum)
            return True, f"Flag «{flag.code}»: {'activo' if flag.active else 'inactivo'}."
        except FeatureFlagsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.change_feature_flag_status failed")
            return False, "Error inesperado; revise el log."

    def request_feature_flag_change(self, **kwargs) -> tuple[bool, str]:
        if self._request_feature_flag_change_uc is None:
            return False, "Solicitud de cambio no disponible."
        actor = self._actor()
        if not actor:
            return False, "Sesión inválida; no se puede solicitar un cambio sin un usuario autenticado."
        denial = self._authorize(ConfiguracionPermissions.FEATURE_FLAGS_EDITAR)
        if denial:
            return False, denial
        try:
            request = self._request_feature_flag_change_uc.execute(requested_by_user_id=actor, **kwargs)
            return True, f"Solicitud {request.id} creada; pendiente de aprobación."
        except FeatureFlagsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.request_feature_flag_change failed")
            return False, "Error inesperado; revise el log."

    def set_default_theme(self, theme_id: str) -> tuple[bool, str]:
        if self._set_default_theme_uc is None:
            return False, "Cambio de tema predeterminado no disponible."
        denial = self._authorize(ConfiguracionPermissions.TEMA_ACTIVAR)
        if denial:
            return False, denial
        try:
            theme = self._set_default_theme_uc.execute(theme_id=theme_id)
            return True, f"«{theme.name}» es ahora el tema predeterminado."
        except AppearanceDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.set_default_theme failed")
            return False, "Error inesperado; revise el log."

    def create_theme(self, **kwargs) -> tuple[bool, str]:
        if self._create_theme_uc is None:
            return False, "Temas no disponibles."
        denial = self._authorize(ConfiguracionPermissions.TEMA_CREAR)
        if denial:
            return False, denial
        try:
            theme = self._create_theme_uc.execute(**kwargs)
            return True, f"Tema «{theme.code}» creado."
        except AppearanceDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.create_theme failed")
            return False, "Error inesperado; revise el log."

    def update_theme(self, **kwargs) -> tuple[bool, str]:
        if self._update_theme_uc is None:
            return False, "Temas no disponibles."
        denial = self._authorize(ConfiguracionPermissions.APARIENCIA_GESTIONAR)
        if denial:
            return False, denial
        try:
            theme = self._update_theme_uc.execute(**kwargs)
            return True, f"Tema «{theme.code}» actualizado."
        except AppearanceDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.update_theme failed")
            return False, "Error inesperado; revise el log."

    def change_theme_status(self, *, theme_id: str, action: str) -> tuple[bool, str]:
        if self._change_theme_status_uc is None:
            return False, "Cambio de estado no disponible."
        try:
            action_enum = ThemeStatusAction(action)
        except ValueError:
            return False, f"Acción de tema desconocida: {action}"
        denial = self._authorize(ConfiguracionPermissions.APARIENCIA_GESTIONAR)
        if denial:
            return False, denial
        try:
            theme = self._change_theme_status_uc.execute(theme_id=theme_id, action=action_enum)
            return True, f"Tema «{theme.code}»: {'activo' if theme.active else 'inactivo'}."
        except AppearanceDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.change_theme_status failed")
            return False, "Error inesperado; revise el log."

    def create_design_token(self, **kwargs) -> tuple[bool, str]:
        if self._create_design_token_uc is None:
            return False, "Tokens no disponibles."
        denial = self._authorize(ConfiguracionPermissions.APARIENCIA_GESTIONAR)
        if denial:
            return False, denial
        try:
            token = self._create_design_token_uc.execute(**kwargs)
            return True, f"Token «{token.token_key}» creado."
        except AppearanceDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.create_design_token failed")
            return False, "Error inesperado; revise el log."

    def update_design_token(self, **kwargs) -> tuple[bool, str]:
        if self._update_design_token_uc is None:
            return False, "Tokens no disponibles."
        denial = self._authorize(ConfiguracionPermissions.APARIENCIA_GESTIONAR)
        if denial:
            return False, denial
        try:
            token = self._update_design_token_uc.execute(**kwargs)
            return True, f"Token «{token.token_key}» actualizado."
        except AppearanceDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.update_design_token failed")
            return False, "Error inesperado; revise el log."

    def create_density_profile(self, **kwargs) -> tuple[bool, str]:
        if self._create_density_profile_uc is None:
            return False, "Perfiles de densidad no disponibles."
        denial = self._authorize(ConfiguracionPermissions.APARIENCIA_GESTIONAR)
        if denial:
            return False, denial
        try:
            profile = self._create_density_profile_uc.execute(**kwargs)
            return True, f"Perfil «{profile.name}» creado."
        except AppearanceDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.create_density_profile failed")
            return False, "Error inesperado; revise el log."

    def update_density_profile(self, **kwargs) -> tuple[bool, str]:
        if self._update_density_profile_uc is None:
            return False, "Perfiles de densidad no disponibles."
        denial = self._authorize(ConfiguracionPermissions.APARIENCIA_GESTIONAR)
        if denial:
            return False, denial
        try:
            profile = self._update_density_profile_uc.execute(**kwargs)
            return True, f"Perfil «{profile.name}» actualizado."
        except AppearanceDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.update_density_profile failed")
            return False, "Error inesperado; revise el log."

    def change_density_profile_status(self, *, profile_id: str, action: str) -> tuple[bool, str]:
        if self._change_density_profile_status_uc is None:
            return False, "Cambio de estado no disponible."
        try:
            action_enum = DensityProfileStatusAction(action)
        except ValueError:
            return False, f"Acción de perfil desconocida: {action}"
        denial = self._authorize(ConfiguracionPermissions.APARIENCIA_GESTIONAR)
        if denial:
            return False, denial
        try:
            profile = self._change_density_profile_status_uc.execute(profile_id=profile_id, action=action_enum)
            return True, f"Perfil «{profile.name}»: {'activo' if profile.active else 'inactivo'}."
        except AppearanceDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.change_density_profile_status failed")
            return False, "Error inesperado; revise el log."

    def create_appearance_preference(self, **kwargs) -> tuple[bool, str]:
        if self._create_appearance_preference_uc is None:
            return False, "Preferencias de apariencia no disponibles."
        denial = self._authorize(ConfiguracionPermissions.APARIENCIA_GESTIONAR)
        if denial:
            return False, denial
        try:
            preference = self._create_appearance_preference_uc.execute(**kwargs)
            return True, f"Preferencia {preference.id} creada."
        except AppearanceDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.create_appearance_preference failed")
            return False, "Error inesperado; revise el log."

    def change_appearance_preference_status(self, *, preference_id: str, action: str) -> tuple[bool, str]:
        if self._change_appearance_preference_status_uc is None:
            return False, "Cambio de estado no disponible."
        try:
            action_enum = AppearancePreferenceStatusAction(action)
        except ValueError:
            return False, f"Acción de preferencia desconocida: {action}"
        denial = self._authorize(ConfiguracionPermissions.APARIENCIA_GESTIONAR)
        if denial:
            return False, denial
        try:
            preference = self._change_appearance_preference_status_uc.execute(
                preference_id=preference_id, action=action_enum)
            return True, f"Preferencia {preference.id}: {'activa' if preference.active else 'inactiva'}."
        except AppearanceDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.change_appearance_preference_status failed")
            return False, "Error inesperado; revise el log."

    def create_cache_expiration_policy(self, **kwargs) -> tuple[bool, str]:
        if self._create_cache_expiration_policy_uc is None:
            return False, "Políticas de expiración no disponibles."
        denial = self._authorize(ConfiguracionPermissions.OFFLINE_GESTIONAR)
        if denial:
            return False, denial
        try:
            policy = self._create_cache_expiration_policy_uc.execute(**kwargs)
            return True, f"Política «{policy.entity_type}» creada."
        except OfflineDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.create_cache_expiration_policy failed")
            return False, "Error inesperado; revise el log."

    def update_cache_expiration_policy(self, **kwargs) -> tuple[bool, str]:
        if self._update_cache_expiration_policy_uc is None:
            return False, "Políticas de expiración no disponibles."
        denial = self._authorize(ConfiguracionPermissions.OFFLINE_GESTIONAR)
        if denial:
            return False, denial
        try:
            policy = self._update_cache_expiration_policy_uc.execute(**kwargs)
            return True, f"Política «{policy.entity_type}» actualizada."
        except OfflineDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.update_cache_expiration_policy failed")
            return False, "Error inesperado; revise el log."

    def change_cache_expiration_policy_status(self, *, policy_id: str, action: str) -> tuple[bool, str]:
        if self._change_cache_expiration_policy_status_uc is None:
            return False, "Cambio de estado no disponible."
        try:
            action_enum = CacheExpirationPolicyStatusAction(action)
        except ValueError:
            return False, f"Acción de política desconocida: {action}"
        denial = self._authorize(ConfiguracionPermissions.OFFLINE_GESTIONAR)
        if denial:
            return False, denial
        try:
            policy = self._change_cache_expiration_policy_status_uc.execute(
                policy_id=policy_id, action=action_enum)
            return True, f"Política «{policy.entity_type}»: {'activa' if policy.active else 'inactiva'}."
        except OfflineDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.change_cache_expiration_policy_status failed")
            return False, "Error inesperado; revise el log."

    def create_user(
        self, *, username: str, full_name: str = "", email: str = "", password: str = "", role: str = "",
        branch_id: str = "", employee_id: str = "", active: bool = True,
    ) -> tuple[bool, str]:
        if self._save_user_uc is None:
            return False, "Usuarios no disponibles."
        actor = self._actor()
        if not actor:
            return False, "Sesión inválida; no se puede crear un usuario sin un usuario autenticado."
        denial = self._authorize(ConfiguracionPermissions.USUARIOS_CREAR)
        if denial:
            return False, denial
        if not password.strip():
            return False, "La contraseña es obligatoria para un usuario nuevo."
        if _bcrypt is None:
            return False, "bcrypt no está instalado; no se puede guardar la contraseña de forma segura."
        password_hash = _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()
        try:
            cmd = SaveUserCommand(
                operation_id=new_uuid(), branch_id=branch_id, user_name=actor,
                username=username, full_name=full_name, email=email, role=role,
                employee_id=employee_id, active=active, password_hash=password_hash,
            )
            result = self._save_user_uc.execute(cmd)
            return True, f"Usuario «{username}» creado."
        except ValueError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.create_user failed")
            return False, "Error inesperado; revise el log."

    def update_user(
        self, *, user_id: str, username: str, full_name: str = "", email: str = "", password: str = "",
        role: str = "", branch_id: str = "", employee_id: str = "", active: bool = True,
    ) -> tuple[bool, str]:
        if self._save_user_uc is None:
            return False, "Usuarios no disponibles."
        actor = self._actor()
        if not actor:
            return False, "Sesión inválida; no se puede editar un usuario sin un usuario autenticado."
        denial = self._authorize(ConfiguracionPermissions.USUARIOS_EDITAR)
        if denial:
            return False, denial
        password_hash = ""
        if password.strip():
            if _bcrypt is None:
                return False, "bcrypt no está instalado; no se puede guardar la contraseña de forma segura."
            password_hash = _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()
        try:
            cmd = SaveUserCommand(
                operation_id=new_uuid(), branch_id=branch_id, user_name=actor,
                user_id=user_id, username=username, full_name=full_name, email=email, role=role,
                employee_id=employee_id, active=active, password_hash=password_hash,
            )
            self._save_user_uc.execute(cmd)
            return True, f"Usuario «{username}» actualizado."
        except ValueError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.update_user failed")
            return False, "Error inesperado; revise el log."

    def set_user_active(self, *, user_id: str, active: bool) -> tuple[bool, str]:
        if self._set_user_active_uc is None:
            return False, "Cambio de estado no disponible."
        actor = self._actor()
        if not actor:
            return False, "Sesión inválida; no se puede cambiar el estado sin un usuario autenticado."
        denial = self._authorize(ConfiguracionPermissions.USUARIOS_ACTIVAR)
        if denial:
            return False, denial
        try:
            cmd = SetUserActiveCommand(
                operation_id=new_uuid(), branch_id=self._session_branch_id(), user_name=actor,
                user_id=user_id, active=active,
            )
            self._set_user_active_uc.execute(cmd)
            return True, f"Usuario {'activado' if active else 'desactivado'}."
        except ValueError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.set_user_active failed")
            return False, "Error inesperado; revise el log."

    def unlock_user(self, user_id: str) -> tuple[bool, str]:
        if self._user_security_service is None:
            return False, "Desbloqueo no disponible."
        actor = self._actor()
        if not actor:
            return False, "Sesión inválida; no se puede desbloquear sin un usuario autenticado."
        try:
            self._user_security_service.unlock_user(user_id, operation_id=new_uuid(), actor_id=actor)
            return True, "Usuario desbloqueado."
        except PermissionError as exc:
            return False, str(exc)
        except ValueError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.unlock_user failed")
            return False, "Error inesperado; revise el log."

    def save_role(self, *, role_id: str = "", name: str, description: str = "") -> tuple[bool, str]:
        if self._save_role_uc is None:
            return False, "Roles no disponibles."
        actor = self._actor()
        if not actor:
            return False, "Sesión inválida; no se puede guardar un rol sin un usuario autenticado."
        denial = self._authorize(
            ConfiguracionPermissions.ROLES_EDITAR if role_id else ConfiguracionPermissions.ROLES_CREAR)
        if denial:
            return False, denial
        try:
            cmd = SaveRoleCommand(
                operation_id=new_uuid(), branch_id=self._session_branch_id(), user_name=actor,
                role_id=role_id, name=name, description=description,
            )
            self._save_role_uc.execute(cmd)
            return True, f"Rol «{name}» guardado."
        except ValueError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.save_role failed")
            return False, "Error inesperado; revise el log."

    def set_installation_branch(self, branch_id: str) -> tuple[bool, str]:
        if self._set_installation_branch_uc is None:
            return False, "Anclaje de sucursal no disponible."
        actor = self._actor()
        if not actor:
            return False, "Sesión inválida; no se puede anclar la instalación sin un usuario autenticado."
        denial = self._authorize(ConfiguracionPermissions.EMPRESA_EDITAR)
        if denial:
            return False, denial
        try:
            cmd = SetInstallationBranchCommand(
                operation_id=new_uuid(), branch_id=branch_id, user_name=actor,
            )
            result = self._set_installation_branch_uc.execute(cmd)
            return True, f"Instalación anclada a «{result.data.get('branch_name', '')}»."
        except ValueError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.set_installation_branch failed")
            return False, "Error inesperado; revise el log."

    def _session_branch_id(self) -> str:
        return str(getattr(self._session, "active_branch_id", None) or "")

    def register_device_profile(self, **kwargs) -> tuple[bool, str]:
        if self._register_device_profile_uc is None:
            return False, "Registro de perfiles no disponible."
        denial = self._authorize(ConfiguracionPermissions.DISPOSITIVOS_CREAR)
        if denial:
            return False, denial
        try:
            profile = self._register_device_profile_uc.execute(**kwargs)
            return True, f"Perfil «{profile.name}» creado."
        except DeviceManagementDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.register_device_profile failed")
            return False, "Error inesperado; revise el log."

    def register_device(self, **kwargs) -> tuple[bool, str]:
        if self._register_device_uc is None:
            return False, "Registro de dispositivos no disponible."
        denial = self._authorize(ConfiguracionPermissions.DISPOSITIVOS_CREAR)
        if denial:
            return False, denial
        try:
            device = self._register_device_uc.execute(**kwargs)
            return True, f"Dispositivo «{device.code}» registrado."
        except DeviceManagementDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.register_device failed")
            return False, "Error inesperado; revise el log."

    def update_device(self, *, device_id: str, name: str, notes: str) -> tuple[bool, str]:
        if self._update_device_uc is None:
            return False, "Edición de dispositivos no disponible."
        denial = self._authorize(ConfiguracionPermissions.DISPOSITIVOS_EDITAR)
        if denial:
            return False, denial
        try:
            device = self._update_device_uc.execute(device_id=device_id, name=name, notes=notes)
            return True, f"Dispositivo «{device.code}» actualizado."
        except DeviceManagementDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.update_device failed")
            return False, "Error inesperado; revise el log."

    def change_device_status(self, *, device_id: str, action: str, reason: str = "") -> tuple[bool, str]:
        if self._change_device_status_uc is None:
            return False, "Cambio de estado no disponible."
        try:
            action_enum = DeviceStatusAction(action)
        except ValueError:
            return False, f"Acción de dispositivo desconocida: {action}"
        denial = self._authorize(_DEVICE_STATUS_PERMISSIONS[action_enum])
        if denial:
            return False, denial
        try:
            before = self._query_service.get_device(device_id)
            device = self._change_device_status_uc.execute(
                device_id=device_id, action=action_enum, reason=reason,
            )
            if action_enum in _DEVICE_STATUS_AUDITED:
                self._record_audit(
                    entity_type="device", entity_id=device_id, action=action_enum.value,
                    before={"status": getattr(before, "status", None)},
                    after={"status": device.status.value}, reason=reason,
                )
            return True, f"Dispositivo «{device.code}»: {device.status.value}."
        except DeviceManagementDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.change_device_status failed")
            return False, "Error inesperado; revise el log."

    def create_document_template(self, **kwargs) -> tuple[bool, str]:
        if self._create_document_template_uc is None:
            return False, "Registro de plantillas no disponible."
        denial = self._authorize(ConfiguracionPermissions.DOCUMENTOS_PLANTILLA_CREAR)
        if denial:
            return False, denial
        try:
            template, version = self._create_document_template_uc.execute(
                created_by_user_id=self._actor(), **kwargs,
            )
            return True, f"Plantilla «{template.name}» creada (versión {version.version}, borrador)."
        except DocumentOutputDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.create_document_template failed")
            return False, "Error inesperado; revise el log."

    def create_next_template_version(self, *, version_id: str, content: str) -> tuple[bool, str]:
        if self._create_next_template_version_uc is None:
            return False, "Creación de versiones no disponible."
        denial = self._authorize(ConfiguracionPermissions.DOCUMENTOS_PLANTILLA_EDITAR)
        if denial:
            return False, denial
        try:
            version = self._create_next_template_version_uc.execute(
                version_id=version_id, content=content, created_by_user_id=self._actor(),
            )
            return True, f"Versión {version.version} creada (borrador)."
        except DocumentOutputDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.create_next_template_version failed")
            return False, "Error inesperado; revise el log."

    def change_template_version_status(
        self, *, version_id: str, action: str, reason: str = "",
    ) -> tuple[bool, str]:
        if self._change_template_version_status_uc is None:
            return False, "Cambio de estado no disponible."
        actor = self._actor()
        if action in ("APPROVE", "ACTIVATE") and not actor:
            return False, "Sesión inválida; no se puede continuar sin un usuario autenticado."
        try:
            action_enum = TemplateVersionAction(action)
        except ValueError:
            return False, f"Acción de plantilla desconocida: {action}"
        denial = self._authorize(_TEMPLATE_STATUS_PERMISSIONS[action_enum])
        if denial:
            return False, denial
        try:
            version = self._change_template_version_status_uc.execute(
                version_id=version_id, action=action_enum, actor_user_id=actor, reason=reason,
            )
            if action_enum in _TEMPLATE_STATUS_AUDITED:
                self._record_audit(
                    entity_type="document_template_version", entity_id=version_id,
                    action=action_enum.value,
                    after={
                        "status": version.status.value,
                        "created_by": version.created_by_user_id,
                        "approved_by": version.approved_by_user_id,
                        "activated_by": version.activated_by_user_id,
                    },
                    reason=reason,
                )
            return True, f"Versión {version.version}: {version.status.value}."
        except DocumentOutputDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.change_template_version_status failed")
            return False, "Error inesperado; revise el log."

    def save_company_profile(self, **kwargs) -> tuple[bool, str]:
        if self._save_company_profile_uc is None:
            return False, "Registro de la empresa no disponible."
        denial = self._authorize(ConfiguracionPermissions.EMPRESA_EDITAR)
        if denial:
            return False, denial
        try:
            company = self._save_company_profile_uc.execute(**kwargs)
            return True, f"Empresa «{company.legal_name}» guardada."
        except ConfigurationDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.save_company_profile failed")
            return False, "Error inesperado; revise el log."

    def register_branch_profile(self, **kwargs) -> tuple[bool, str]:
        if self._register_branch_profile_uc is None:
            return False, "Registro de sucursales no disponible."
        denial = self._authorize(ConfiguracionPermissions.SUCURSAL_CREAR)
        if denial:
            return False, denial
        try:
            branch = self._register_branch_profile_uc.execute(**kwargs)
            return True, f"Sucursal «{branch.name}» registrada."
        except ConfigurationDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.register_branch_profile failed")
            return False, "Error inesperado; revise el log."

    def update_branch_profile(self, **kwargs) -> tuple[bool, str]:
        if self._update_branch_profile_uc is None:
            return False, "Edición de sucursales no disponible."
        denial = self._authorize(ConfiguracionPermissions.SUCURSAL_EDITAR)
        if denial:
            return False, denial
        try:
            branch = self._update_branch_profile_uc.execute(**kwargs)
            return True, f"Sucursal «{branch.name}» actualizada."
        except ConfigurationDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.update_branch_profile failed")
            return False, "Error inesperado; revise el log."

    def register_workstation(self, **kwargs) -> tuple[bool, str]:
        if self._register_workstation_uc is None:
            return False, "Registro de estaciones no disponible."
        denial = self._authorize(ConfiguracionPermissions.ESTACION_CREAR)
        if denial:
            return False, denial
        try:
            workstation = self._register_workstation_uc.execute(**kwargs)
            return True, f"Estación «{workstation.code}» registrada."
        except ConfigurationDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.register_workstation failed")
            return False, "Error inesperado; revise el log."

    def update_workstation(self, **kwargs) -> tuple[bool, str]:
        if self._update_workstation_uc is None:
            return False, "Edición de estaciones no disponible."
        denial = self._authorize(ConfiguracionPermissions.ESTACION_EDITAR)
        if denial:
            return False, denial
        try:
            workstation = self._update_workstation_uc.execute(**kwargs)
            return True, f"Estación «{workstation.code}» actualizada."
        except ConfigurationDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.update_workstation failed")
            return False, "Error inesperado; revise el log."

    def change_workstation_status(
        self, *, workstation_id: str, action: str, reason: str = "",
    ) -> tuple[bool, str]:
        if self._change_workstation_status_uc is None:
            return False, "Cambio de estado no disponible."
        try:
            action_enum = WorkstationStatusAction(action)
        except ValueError:
            return False, f"Acción de estación desconocida: {action}"
        denial = self._authorize(_WORKSTATION_STATUS_PERMISSIONS[action_enum])
        if denial:
            return False, denial
        try:
            before = self._query_service.get_workstation(workstation_id)
            workstation = self._change_workstation_status_uc.execute(
                workstation_id=workstation_id, action=action_enum, reason=reason,
            )
            if action_enum in _WORKSTATION_STATUS_AUDITED:
                self._record_audit(
                    entity_type="workstation", entity_id=workstation_id, action=action_enum.value,
                    before={"status": getattr(before, "status", None)},
                    after={"status": workstation.status.value}, reason=reason,
                )
            return True, f"Estación «{workstation.code}»: {workstation.status.value}."
        except ConfigurationDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.change_workstation_status failed")
            return False, "Error inesperado; revise el log."

    def assign_device(self, **kwargs) -> tuple[bool, str]:
        if self._assign_device_uc is None:
            return False, "Asignación de dispositivos no disponible."
        denial = self._authorize(ConfiguracionPermissions.DISPOSITIVOS_ASIGNAR)
        if denial:
            return False, denial
        try:
            assignment = self._assign_device_uc.execute(assigned_by_user_id=self._actor(), **kwargs)
            self._record_audit(
                entity_type="workstation_device_assignment", entity_id=assignment.id, action="ASSIGN",
                after={
                    "workstation_id": assignment.workstation_id, "device_id": assignment.device_id,
                    "role": assignment.role.value,
                },
            )
            return True, f"Dispositivo asignado al rol {assignment.role.value}."
        except DeviceManagementDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.assign_device failed")
            return False, "Error inesperado; revise el log."

    def unassign_device(self, *, assignment_id: str) -> tuple[bool, str]:
        if self._unassign_device_uc is None:
            return False, "Desasignación de dispositivos no disponible."
        denial = self._authorize(ConfiguracionPermissions.DISPOSITIVOS_ASIGNAR)
        if denial:
            return False, denial
        try:
            assignment = self._unassign_device_uc.execute(assignment_id=assignment_id)
            self._record_audit(
                entity_type="workstation_device_assignment", entity_id=assignment.id, action="UNASSIGN",
                before={
                    "workstation_id": assignment.workstation_id, "device_id": assignment.device_id,
                    "role": assignment.role.value,
                },
            )
            return True, f"Dispositivo desasignado del rol {assignment.role.value}."
        except DeviceManagementDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.unassign_device failed")
            return False, "Error inesperado; revise el log."

    def create_print_route(self, **kwargs) -> tuple[bool, str]:
        if self._create_print_route_uc is None:
            return False, "Rutas de impresión no disponibles."
        denial = self._authorize(ConfiguracionPermissions.DISPOSITIVOS_RUTAS_GESTIONAR)
        if denial:
            return False, denial
        try:
            route = self._create_print_route_uc.execute(**kwargs)
            self._record_audit(
                entity_type="print_route", entity_id=route.id, action="CREATE",
                after={
                    "document_type": route.document_type, "primary_device_id": route.primary_device_id,
                    "fallback_device_ids": list(route.fallback_device_ids),
                },
            )
            return True, f"Ruta de impresión para {route.document_type} creada."
        except DeviceManagementDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.create_print_route failed")
            return False, "Error inesperado; revise el log."

    def update_print_route(self, **kwargs) -> tuple[bool, str]:
        if self._update_print_route_uc is None:
            return False, "Rutas de impresión no disponibles."
        denial = self._authorize(ConfiguracionPermissions.DISPOSITIVOS_RUTAS_GESTIONAR)
        if denial:
            return False, denial
        try:
            route = self._update_print_route_uc.execute(**kwargs)
            self._record_audit(
                entity_type="print_route", entity_id=route.id, action="UPDATE",
                after={
                    "primary_device_id": route.primary_device_id,
                    "fallback_device_ids": list(route.fallback_device_ids),
                },
            )
            return True, f"Ruta de impresión para {route.document_type} actualizada."
        except DeviceManagementDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.update_print_route failed")
            return False, "Error inesperado; revise el log."

    def change_print_route_status(self, *, route_id: str, action: str) -> tuple[bool, str]:
        if self._change_print_route_status_uc is None:
            return False, "Rutas de impresión no disponibles."
        try:
            action_enum = PrintRouteStatusAction(action)
        except ValueError:
            return False, f"Acción de ruta desconocida: {action}"
        denial = self._authorize(ConfiguracionPermissions.DISPOSITIVOS_RUTAS_GESTIONAR)
        if denial:
            return False, denial
        try:
            route = self._change_print_route_status_uc.execute(route_id=route_id, action=action_enum)
            self._record_audit(
                entity_type="print_route", entity_id=route.id, action=action_enum.value,
                after={"active": route.active},
            )
            return True, f"Ruta de impresión para {route.document_type}: {'activa' if route.active else 'inactiva'}."
        except DeviceManagementDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.change_print_route_status failed")
            return False, "Error inesperado; revise el log."

    def update_document_template(self, **kwargs) -> tuple[bool, str]:
        if self._update_document_template_uc is None:
            return False, "Edición de plantillas no disponible."
        denial = self._authorize(ConfiguracionPermissions.DOCUMENTOS_PLANTILLA_EDITAR)
        if denial:
            return False, denial
        try:
            template = self._update_document_template_uc.execute(**kwargs)
            return True, f"Plantilla «{template.name}» actualizada."
        except DocumentOutputDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.update_document_template failed")
            return False, "Error inesperado; revise el log."

    def change_document_template_status(self, *, template_id: str, action: str) -> tuple[bool, str]:
        if self._change_document_template_status_uc is None:
            return False, "Cambio de estado no disponible."
        try:
            action_enum = DocumentTemplateStatusAction(action)
        except ValueError:
            return False, f"Acción de plantilla desconocida: {action}"
        denial = self._authorize(_DOCUMENT_TEMPLATE_STATUS_PERMISSION)
        if denial:
            return False, denial
        try:
            template = self._change_document_template_status_uc.execute(
                template_id=template_id, action=action_enum,
            )
            self._record_audit(
                entity_type="document_template", entity_id=template.id, action=action_enum.value,
                after={"active": template.active},
            )
            return True, f"Plantilla «{template.name}»: {'activa' if template.active else 'inactiva'}."
        except DocumentOutputDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.change_document_template_status failed")
            return False, "Error inesperado; revise el log."

    def create_marketing_campaign(self, **kwargs) -> tuple[bool, str]:
        if self._create_marketing_campaign_uc is None:
            return False, "Campañas de marketing no disponibles."
        denial = self._authorize(ConfiguracionPermissions.DOCUMENTOS_CAMPANA_CREAR)
        if denial:
            return False, denial
        try:
            campaign = self._create_marketing_campaign_uc.execute(**kwargs)
            return True, f"Campaña «{campaign.code}» creada."
        except DocumentOutputDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.create_marketing_campaign failed")
            return False, "Error inesperado; revise el log."

    def update_marketing_campaign(self, **kwargs) -> tuple[bool, str]:
        if self._update_marketing_campaign_uc is None:
            return False, "Campañas de marketing no disponibles."
        denial = self._authorize(ConfiguracionPermissions.DOCUMENTOS_CAMPANA_EDITAR)
        if denial:
            return False, denial
        try:
            campaign = self._update_marketing_campaign_uc.execute(**kwargs)
            return True, f"Campaña «{campaign.code}» actualizada."
        except DocumentOutputDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.update_marketing_campaign failed")
            return False, "Error inesperado; revise el log."

    def change_marketing_campaign_status(self, *, campaign_id: str, action: str) -> tuple[bool, str]:
        if self._change_marketing_campaign_status_uc is None:
            return False, "Cambio de estado no disponible."
        try:
            action_enum = MarketingCampaignStatusAction(action)
        except ValueError:
            return False, f"Acción de campaña desconocida: {action}"
        denial = self._authorize(_CAMPAIGN_STATUS_PERMISSION)
        if denial:
            return False, denial
        try:
            campaign = self._change_marketing_campaign_status_uc.execute(
                campaign_id=campaign_id, action=action_enum,
            )
            self._record_audit(
                entity_type="marketing_campaign", entity_id=campaign.id, action=action_enum.value,
                after={"active": campaign.active},
            )
            return True, f"Campaña «{campaign.code}»: {'activa' if campaign.active else 'inactiva'}."
        except DocumentOutputDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.change_marketing_campaign_status failed")
            return False, "Error inesperado; revise el log."

    # ── Pantalla del cliente: Contenido/Campañas/Slots/Asignaciones (SET-18) ──

    def create_display_content(self, **kwargs) -> tuple[bool, str]:
        if self._create_content_uc is None:
            return False, "Contenido no disponible."
        denial = self._authorize(ConfiguracionPermissions.PANTALLA_CLIENTE_CONTENIDO_CREAR)
        if denial:
            return False, denial
        try:
            content = self._create_content_uc.execute(**kwargs)
            return True, f"Contenido «{content.title}» creado."
        except CustomerDisplayDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.create_display_content failed")
            return False, "Error inesperado; revise el log."

    def update_display_content(self, **kwargs) -> tuple[bool, str]:
        if self._update_content_uc is None:
            return False, "Contenido no disponible."
        denial = self._authorize(ConfiguracionPermissions.PANTALLA_CLIENTE_CONTENIDO_CREAR)
        if denial:
            return False, denial
        try:
            content = self._update_content_uc.execute(**kwargs)
            return True, f"Contenido «{content.title}» actualizado."
        except CustomerDisplayDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.update_display_content failed")
            return False, "Error inesperado; revise el log."

    def change_display_content_status(self, *, content_id: str, action: str) -> tuple[bool, str]:
        if self._change_content_status_uc is None:
            return False, "Cambio de estado no disponible."
        try:
            action_enum = ContentStatusAction(action)
        except ValueError:
            return False, f"Acción de contenido desconocida: {action}"
        denial = self._authorize(ConfiguracionPermissions.PANTALLA_CLIENTE_CONTENIDO_CREAR)
        if denial:
            return False, denial
        try:
            content = self._change_content_status_uc.execute(content_id=content_id, action=action_enum)
            return True, f"Contenido «{content.title}»: {'activo' if content.active else 'inactivo'}."
        except CustomerDisplayDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.change_display_content_status failed")
            return False, "Error inesperado; revise el log."

    def create_content_campaign(self, **kwargs) -> tuple[bool, str]:
        if self._create_content_campaign_uc is None:
            return False, "Campañas de contenido no disponibles."
        denial = self._authorize(ConfiguracionPermissions.PANTALLA_CLIENTE_CAMPANA_PROGRAMAR)
        if denial:
            return False, denial
        try:
            campaign = self._create_content_campaign_uc.execute(
                created_by_user_id=self._actor() or None, **kwargs,
            )
            return True, f"Campaña «{campaign.name}» creada."
        except CustomerDisplayDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.create_content_campaign failed")
            return False, "Error inesperado; revise el log."

    def update_content_campaign(self, **kwargs) -> tuple[bool, str]:
        if self._update_content_campaign_uc is None:
            return False, "Campañas de contenido no disponibles."
        denial = self._authorize(ConfiguracionPermissions.PANTALLA_CLIENTE_CAMPANA_PROGRAMAR)
        if denial:
            return False, denial
        try:
            campaign = self._update_content_campaign_uc.execute(**kwargs)
            return True, f"Campaña «{campaign.name}» actualizada."
        except CustomerDisplayDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.update_content_campaign failed")
            return False, "Error inesperado; revise el log."

    def change_content_campaign_status(self, *, campaign_id: str, action: str, reason: str = "") -> tuple[bool, str]:
        if self._change_content_campaign_status_uc is None:
            return False, "Cambio de estado no disponible."
        actor = self._actor()
        if action in ("APPROVE", "ACTIVATE") and not actor:
            return False, "Sesión inválida; no se puede continuar sin un usuario autenticado."
        try:
            action_enum = ContentCampaignStatusAction(action)
        except ValueError:
            return False, f"Acción de campaña desconocida: {action}"
        denial = self._authorize(_CONTENT_CAMPAIGN_STATUS_PERMISSIONS[action_enum])
        if denial:
            return False, denial
        try:
            campaign = self._change_content_campaign_status_uc.execute(
                campaign_id=campaign_id, action=action_enum, actor_user_id=actor, reason=reason,
            )
            if action_enum in _CONTENT_CAMPAIGN_STATUS_AUDITED:
                self._record_audit(
                    entity_type="content_campaign", entity_id=campaign_id, action=action_enum.value,
                    after={
                        "status": campaign.status.value, "created_by": campaign.created_by_user_id,
                        "approved_by": campaign.approved_by_user_id,
                        "activated_by": campaign.activated_by_user_id,
                    },
                    reason=reason,
                )
            return True, f"Campaña «{campaign.name}»: {campaign.status.value}."
        except CustomerDisplayDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.change_content_campaign_status failed")
            return False, "Error inesperado; revise el log."

    def create_advertising_slot(self, **kwargs) -> tuple[bool, str]:
        if self._create_advertising_slot_uc is None:
            return False, "Slots publicitarios no disponibles."
        denial = self._authorize(ConfiguracionPermissions.PANTALLA_CLIENTE_PUBLICIDAD_GESTIONAR)
        if denial:
            return False, denial
        try:
            slot = self._create_advertising_slot_uc.execute(**kwargs)
            return True, f"Slot «{slot.code}» creado."
        except CustomerDisplayDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.create_advertising_slot failed")
            return False, "Error inesperado; revise el log."

    def update_advertising_slot(self, **kwargs) -> tuple[bool, str]:
        if self._update_advertising_slot_uc is None:
            return False, "Slots publicitarios no disponibles."
        denial = self._authorize(ConfiguracionPermissions.PANTALLA_CLIENTE_PUBLICIDAD_GESTIONAR)
        if denial:
            return False, denial
        try:
            slot = self._update_advertising_slot_uc.execute(**kwargs)
            return True, f"Slot «{slot.code}» actualizado."
        except CustomerDisplayDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.update_advertising_slot failed")
            return False, "Error inesperado; revise el log."

    def change_advertising_slot_status(self, *, slot_id: str, action: str) -> tuple[bool, str]:
        if self._change_advertising_slot_status_uc is None:
            return False, "Cambio de estado no disponible."
        try:
            action_enum = AdvertisingSlotStatusAction(action)
        except ValueError:
            return False, f"Acción de slot desconocida: {action}"
        denial = self._authorize(ConfiguracionPermissions.PANTALLA_CLIENTE_PUBLICIDAD_GESTIONAR)
        if denial:
            return False, denial
        try:
            slot = self._change_advertising_slot_status_uc.execute(slot_id=slot_id, action=action_enum)
            return True, f"Slot «{slot.code}»: {'activo' if slot.active else 'inactivo'}."
        except CustomerDisplayDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.change_advertising_slot_status failed")
            return False, "Error inesperado; revise el log."

    def assign_campaign_placement(self, **kwargs) -> tuple[bool, str]:
        if self._assign_campaign_placement_uc is None:
            return False, "Asignaciones no disponibles."
        denial = self._authorize(ConfiguracionPermissions.PANTALLA_CLIENTE_PUBLICIDAD_GESTIONAR)
        if denial:
            return False, denial
        try:
            placement = self._assign_campaign_placement_uc.execute(
                assigned_by_user_id=self._actor() or None, **kwargs,
            )
            return True, f"Asignación creada (placement {placement.id})."
        except CustomerDisplayDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.assign_campaign_placement failed")
            return False, "Error inesperado; revise el log."

    def unassign_campaign_placement(self, *, placement_id: str) -> tuple[bool, str]:
        if self._unassign_campaign_placement_uc is None:
            return False, "Asignaciones no disponibles."
        denial = self._authorize(ConfiguracionPermissions.PANTALLA_CLIENTE_PUBLICIDAD_GESTIONAR)
        if denial:
            return False, denial
        try:
            self._unassign_campaign_placement_uc.execute(placement_id=placement_id)
            return True, "Asignación liberada."
        except CustomerDisplayDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.unassign_campaign_placement failed")
            return False, "Error inesperado; revise el log."

    # ── Integraciones: Definitions/Instances/Credentials/Health/Webhooks (SET-19) ──

    def create_integration_definition(self, **kwargs) -> tuple[bool, str]:
        if self._create_integration_definition_uc is None:
            return False, "Integraciones no disponibles."
        denial = self._authorize(ConfiguracionPermissions.INTEGRACIONES_CREAR)
        if denial:
            return False, denial
        try:
            definition = self._create_integration_definition_uc.execute(**kwargs)
            return True, f"Definición «{definition.name}» creada."
        except IntegrationsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.create_integration_definition failed")
            return False, "Error inesperado; revise el log."

    def update_integration_definition(self, **kwargs) -> tuple[bool, str]:
        if self._update_integration_definition_uc is None:
            return False, "Integraciones no disponibles."
        denial = self._authorize(ConfiguracionPermissions.INTEGRACIONES_EDITAR)
        if denial:
            return False, denial
        try:
            definition = self._update_integration_definition_uc.execute(**kwargs)
            return True, f"Definición «{definition.name}» actualizada."
        except IntegrationsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.update_integration_definition failed")
            return False, "Error inesperado; revise el log."

    def change_integration_definition_status(self, *, definition_id: str, action: str) -> tuple[bool, str]:
        if self._change_integration_definition_status_uc is None:
            return False, "Cambio de estado no disponible."
        try:
            action_enum = IntegrationDefinitionStatusAction(action)
        except ValueError:
            return False, f"Acción de definición desconocida: {action}"
        permission = (
            ConfiguracionPermissions.INTEGRACIONES_ACTIVAR if action_enum is IntegrationDefinitionStatusAction.ACTIVATE
            else ConfiguracionPermissions.INTEGRACIONES_DESACTIVAR
        )
        denial = self._authorize(permission)
        if denial:
            return False, denial
        try:
            definition = self._change_integration_definition_status_uc.execute(
                definition_id=definition_id, action=action_enum,
            )
            return True, f"Definición «{definition.name}»: {'activa' if definition.active else 'inactiva'}."
        except IntegrationsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.change_integration_definition_status failed")
            return False, "Error inesperado; revise el log."

    def create_integration_instance(self, **kwargs) -> tuple[bool, str]:
        if self._create_integration_instance_uc is None:
            return False, "Integraciones no disponibles."
        denial = self._authorize(ConfiguracionPermissions.INTEGRACIONES_CREAR)
        if denial:
            return False, denial
        try:
            instance = self._create_integration_instance_uc.execute(**kwargs)
            return True, f"Instancia «{instance.name}» creada."
        except IntegrationsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.create_integration_instance failed")
            return False, "Error inesperado; revise el log."

    def update_integration_instance(self, **kwargs) -> tuple[bool, str]:
        if self._update_integration_instance_uc is None:
            return False, "Integraciones no disponibles."
        denial = self._authorize(ConfiguracionPermissions.INTEGRACIONES_EDITAR)
        if denial:
            return False, denial
        try:
            instance = self._update_integration_instance_uc.execute(**kwargs)
            return True, f"Instancia «{instance.name}» actualizada."
        except IntegrationsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.update_integration_instance failed")
            return False, "Error inesperado; revise el log."

    def change_integration_instance_status(self, *, instance_id: str, action: str) -> tuple[bool, str]:
        if self._change_integration_instance_status_uc is None:
            return False, "Cambio de estado no disponible."
        try:
            action_enum = IntegrationInstanceStatusAction(action)
        except ValueError:
            return False, f"Acción de instancia desconocida: {action}"
        permission = (
            ConfiguracionPermissions.INTEGRACIONES_ACTIVAR if action_enum is IntegrationInstanceStatusAction.ACTIVATE
            else ConfiguracionPermissions.INTEGRACIONES_DESACTIVAR
        )
        denial = self._authorize(permission)
        if denial:
            return False, denial
        try:
            instance = self._change_integration_instance_status_uc.execute(
                instance_id=instance_id, action=action_enum,
            )
            return True, f"Instancia «{instance.name}»: {'activa' if instance.active else 'inactiva'}."
        except IntegrationsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.change_integration_instance_status failed")
            return False, "Error inesperado; revise el log."

    def set_integration_instance_credential(self, **kwargs) -> tuple[bool, str]:
        if self._set_integration_instance_credential_uc is None:
            return False, "Credenciales no disponibles."
        denial = self._authorize(ConfiguracionPermissions.INTEGRACIONES_SECRETOS)
        if denial:
            return False, denial
        try:
            instance = self._set_integration_instance_credential_uc.execute(**kwargs)
            self._record_audit(
                entity_type="integration_instance", entity_id=instance.id, action="SET_CREDENTIAL",
                after={"credential_references": list(instance.credential_references)},
            )
            return True, "Credencial configurada."
        except IntegrationsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.set_integration_instance_credential failed")
            return False, "Error inesperado; revise el log."

    def create_webhook_endpoint(self, **kwargs) -> tuple[bool, str]:
        if self._create_webhook_endpoint_uc is None:
            return False, "Webhooks no disponibles."
        denial = self._authorize(ConfiguracionPermissions.WEBHOOKS_GESTIONAR)
        if denial:
            return False, denial
        try:
            endpoint = self._create_webhook_endpoint_uc.execute(**kwargs)
            return True, f"Webhook «{endpoint.code}» creado."
        except IntegrationsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.create_webhook_endpoint failed")
            return False, "Error inesperado; revise el log."

    def change_webhook_endpoint_status(self, *, endpoint_id: str, action: str) -> tuple[bool, str]:
        if self._change_webhook_endpoint_status_uc is None:
            return False, "Cambio de estado no disponible."
        try:
            action_enum = WebhookEndpointStatusAction(action)
        except ValueError:
            return False, f"Acción de webhook desconocida: {action}"
        denial = self._authorize(ConfiguracionPermissions.WEBHOOKS_GESTIONAR)
        if denial:
            return False, denial
        try:
            endpoint = self._change_webhook_endpoint_status_uc.execute(endpoint_id=endpoint_id, action=action_enum)
            return True, f"Webhook «{endpoint.code}»: {'activo' if endpoint.active else 'inactivo'}."
        except IntegrationsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.change_webhook_endpoint_status failed")
            return False, "Error inesperado; revise el log."

    def record_integration_health_check(self, **kwargs) -> tuple[bool, str]:
        if self._record_integration_health_check_uc is None:
            return False, "Chequeos de salud no disponibles."
        denial = self._authorize(ConfiguracionPermissions.INTEGRACIONES_PROBAR)
        if denial:
            return False, denial
        try:
            check = self._record_integration_health_check_uc.execute(**kwargs)
            return True, f"Chequeo registrado: {'éxito' if check.success else 'falla'}."
        except IntegrationsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.record_integration_health_check failed")
            return False, "Error inesperado; revise el log."

    # ── Notificaciones: Accounts/Templates/Channels/Routing (SET-20) ────────

    def create_notification_account(self, **kwargs) -> tuple[bool, str]:
        if self._create_notification_account_uc is None:
            return False, "Notificaciones no disponibles."
        denial = self._authorize(ConfiguracionPermissions.NOTIFICACIONES_GESTIONAR)
        if denial:
            return False, denial
        try:
            account = self._create_notification_account_uc.execute(**kwargs)
            return True, f"Cuenta «{account.name}» creada."
        except NotificationsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.create_notification_account failed")
            return False, "Error inesperado; revise el log."

    def update_notification_account(self, **kwargs) -> tuple[bool, str]:
        if self._update_notification_account_uc is None:
            return False, "Notificaciones no disponibles."
        denial = self._authorize(ConfiguracionPermissions.NOTIFICACIONES_GESTIONAR)
        if denial:
            return False, denial
        try:
            account = self._update_notification_account_uc.execute(**kwargs)
            return True, f"Cuenta «{account.name}» actualizada."
        except NotificationsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.update_notification_account failed")
            return False, "Error inesperado; revise el log."

    def change_notification_account_status(self, *, account_id: str, action: str) -> tuple[bool, str]:
        if self._change_notification_account_status_uc is None:
            return False, "Cambio de estado no disponible."
        try:
            action_enum = NotificationAccountStatusAction(action)
        except ValueError:
            return False, f"Acción de cuenta desconocida: {action}"
        denial = self._authorize(ConfiguracionPermissions.NOTIFICACIONES_GESTIONAR)
        if denial:
            return False, denial
        try:
            account = self._change_notification_account_status_uc.execute(account_id=account_id, action=action_enum)
            return True, f"Cuenta «{account.name}»: {'activa' if account.active else 'inactiva'}."
        except NotificationsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.change_notification_account_status failed")
            return False, "Error inesperado; revise el log."

    def create_notification_template(self, **kwargs) -> tuple[bool, str]:
        if self._create_notification_template_uc is None:
            return False, "Notificaciones no disponibles."
        denial = self._authorize(ConfiguracionPermissions.NOTIFICACIONES_GESTIONAR)
        if denial:
            return False, denial
        try:
            template = self._create_notification_template_uc.execute(**kwargs)
            return True, f"Plantilla «{template.code}» creada."
        except NotificationsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.create_notification_template failed")
            return False, "Error inesperado; revise el log."

    def update_notification_template(self, **kwargs) -> tuple[bool, str]:
        if self._update_notification_template_uc is None:
            return False, "Notificaciones no disponibles."
        denial = self._authorize(ConfiguracionPermissions.NOTIFICACIONES_GESTIONAR)
        if denial:
            return False, denial
        try:
            template = self._update_notification_template_uc.execute(**kwargs)
            return True, f"Plantilla «{template.code}» actualizada."
        except NotificationsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.update_notification_template failed")
            return False, "Error inesperado; revise el log."

    def change_notification_template_status(self, *, template_id: str, action: str) -> tuple[bool, str]:
        if self._change_notification_template_status_uc is None:
            return False, "Cambio de estado no disponible."
        try:
            action_enum = NotificationTemplateStatusAction(action)
        except ValueError:
            return False, f"Acción de plantilla desconocida: {action}"
        denial = self._authorize(ConfiguracionPermissions.NOTIFICACIONES_GESTIONAR)
        if denial:
            return False, denial
        try:
            template = self._change_notification_template_status_uc.execute(
                template_id=template_id, action=action_enum)
            return True, f"Plantilla «{template.code}»: {'activa' if template.active else 'inactiva'}."
        except NotificationsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.change_notification_template_status failed")
            return False, "Error inesperado; revise el log."

    def create_notification_route(self, **kwargs) -> tuple[bool, str]:
        if self._create_notification_route_uc is None:
            return False, "Notificaciones no disponibles."
        denial = self._authorize(ConfiguracionPermissions.NOTIFICACIONES_GESTIONAR)
        if denial:
            return False, denial
        try:
            route = self._create_notification_route_uc.execute(**kwargs)
            return True, f"Ruta «{route.event_code}» creada."
        except NotificationsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.create_notification_route failed")
            return False, "Error inesperado; revise el log."

    def change_notification_route_status(self, *, route_id: str, action: str) -> tuple[bool, str]:
        if self._change_notification_route_status_uc is None:
            return False, "Cambio de estado no disponible."
        try:
            action_enum = NotificationRouteStatusAction(action)
        except ValueError:
            return False, f"Acción de ruta desconocida: {action}"
        denial = self._authorize(ConfiguracionPermissions.NOTIFICACIONES_GESTIONAR)
        if denial:
            return False, denial
        try:
            route = self._change_notification_route_status_uc.execute(route_id=route_id, action=action_enum)
            return True, f"Ruta «{route.event_code}»: {'activa' if route.active else 'inactiva'}."
        except NotificationsDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("ConfiguracionPresenter.change_notification_route_status failed")
            return False, "Error inesperado; revise el log."
