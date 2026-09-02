"""Read models for the Configuración desktop workspace — UI/UX phase.

Mirrors `backend/application/transfers/queries/workspace_query_service.py`'s
shape: one `page(page_id, search)` entry point, one row shape, dispatching
internally per section. Unlike Transfers (one uniform table layout across
every internal page), Configuración's 9 sections have different column
counts/meanings, so `ConfigColumnDTO`/`ConfigPageViewModel` carry column
headers as data instead of assuming a fixed layout — still framework-
agnostic (no PyQt import here; the UI maps `ConfigColumnDTO` to a real
`ColumnSpec` widget).

This is the first read path wired against the 9 bounded contexts built in
SET-0..23 (`backend/domain/settings/…/offline/`) — no UI existed for any
of them before this phase (verified: nothing under `frontend/desktop/` or
`modulos/` imported any of those packages).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.dto.configuracion_dtos import RoleSettingsDTO, UserSettingsDTO
from backend.domain.appearance.enums import ThemeMode
from backend.domain.customer_display.policies.impression_metrics_policy import summarize_impressions
from backend.infrastructure.db.repositories.appearance.appearance_preference_repository import (
    SqliteAppearancePreferenceRepository,
)
from backend.infrastructure.db.repositories.appearance.density_profile_repository import (
    SqliteDensityProfileRepository,
)
from backend.infrastructure.db.repositories.appearance.design_token_repository import (
    SqliteDesignTokenRepository,
)
from backend.infrastructure.db.repositories.appearance.theme_repository import SqliteThemeRepository
from backend.infrastructure.db.repositories.customer_display.advertising_slot_repository import (
    SqliteAdvertisingSlotRepository,
)
from backend.infrastructure.db.repositories.customer_display.campaign_placement_repository import (
    SqliteCampaignPlacementRepository,
)
from backend.infrastructure.db.repositories.customer_display.content_campaign_repository import (
    SqliteContentCampaignRepository,
)
from backend.infrastructure.db.repositories.customer_display.content_impression_repository import (
    SqliteContentImpressionRepository,
)
from backend.infrastructure.db.repositories.customer_display.content_repository import (
    SqliteContentRepository,
)
from backend.infrastructure.db.repositories.customer_display.customer_display_repository import (
    SqliteCustomerDisplayRepository,
)
from backend.infrastructure.db.repositories.device_management.device_profile_repository import (
    SqliteDeviceProfileRepository,
)
from backend.infrastructure.db.repositories.device_management.device_repository import (
    SqliteDeviceRepository,
)
from backend.infrastructure.db.repositories.device_management.print_route_repository import (
    SqlitePrintRouteRepository,
)
from backend.infrastructure.db.repositories.device_management.workstation_device_assignment_repository import (
    SqliteWorkstationDeviceAssignmentRepository,
)
from backend.infrastructure.db.repositories.document_output.document_template_repository import (
    SqliteDocumentTemplateRepository,
)
from backend.infrastructure.db.repositories.document_output.document_template_version_repository import (
    SqliteDocumentTemplateVersionRepository,
)
from backend.infrastructure.db.repositories.document_output.marketing_campaign_repository import (
    SqliteMarketingCampaignRepository,
)
from backend.infrastructure.db.repositories.feature_flags.feature_flag_change_request_repository import (
    SqliteFeatureFlagChangeRequestRepository,
)
from backend.infrastructure.db.repositories.feature_flags.feature_flag_repository import (
    SqliteFeatureFlagRepository,
)
from backend.infrastructure.db.repositories.feature_flags.feature_flag_rule_repository import (
    SqliteFeatureFlagRuleRepository,
)
from backend.infrastructure.db.repositories.integrations.integration_definition_repository import (
    SqliteIntegrationDefinitionRepository,
)
from backend.infrastructure.db.repositories.integrations.integration_health_check_repository import (
    SqliteIntegrationHealthCheckRepository,
)
from backend.infrastructure.db.repositories.integrations.integration_instance_repository import (
    SqliteIntegrationInstanceRepository,
)
from backend.infrastructure.db.repositories.integrations.webhook_endpoint_repository import (
    SqliteWebhookEndpointRepository,
)
from backend.infrastructure.db.repositories.notifications.notification_account_repository import (
    SqliteNotificationAccountRepository,
)
from backend.infrastructure.db.repositories.notifications.notification_route_repository import (
    SqliteNotificationRouteRepository,
)
from backend.infrastructure.db.repositories.notifications.notification_template_repository import (
    SqliteNotificationTemplateRepository,
)
from backend.infrastructure.db.repositories.offline.cache_expiration_policy_repository import (
    SqliteCacheExpirationPolicyRepository,
)
from backend.infrastructure.db.repositories.offline.offline_cache_entry_repository import (
    SqliteOfflineCacheEntryRepository,
)
from backend.infrastructure.db.repositories.settings.branch_profile_repository import (
    SqliteBranchProfileRepository,
)
from backend.infrastructure.db.repositories.settings.company_profile_repository import (
    SqliteCompanyProfileRepository,
)
from backend.infrastructure.db.repositories.settings.workstation_repository import (
    SqliteWorkstationRepository,
)


@dataclass(frozen=True, slots=True)
class ConfigColumnDTO:
    title: str
    kind: str = "text"


@dataclass(frozen=True, slots=True)
class ConfigRowViewModel:
    entity_id: str
    cells: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ConfigPageViewModel:
    columns: tuple[ConfigColumnDTO, ...]
    rows: tuple[ConfigRowViewModel, ...] = ()
    empty_message: str = "No hay información disponible."


@dataclass(frozen=True, slots=True)
class ChangeRequestRowViewModel:
    entity_id: str
    flag_code: str
    scope: str
    proposed_enabled: str
    requested_by: str


@dataclass(frozen=True, slots=True)
class FeatureFlagRowViewModel:
    entity_id: str
    code: str
    name: str
    description: str
    default_enabled: bool
    active: bool


@dataclass(frozen=True, slots=True)
class FeatureFlagRuleRowViewModel:
    entity_id: str
    scope_type: str
    scope_id: str | None
    enabled: bool
    rollout_percentage: int
    active: bool


@dataclass(frozen=True, slots=True)
class ThemeRowViewModel:
    entity_id: str
    code: str
    name: str
    mode: str
    is_default: bool


@dataclass(frozen=True, slots=True)
class DesignTokenRowViewModel:
    entity_id: str
    theme_id: str | None
    token_key: str
    category: str
    token_value: str


@dataclass(frozen=True, slots=True)
class DensityProfileRowViewModel:
    entity_id: str
    level: str
    name: str
    scale_factor: str
    control_height_px: int
    touch_target_px: int
    spacing_unit_px: int
    active: bool


@dataclass(frozen=True, slots=True)
class AppearancePreferenceRowViewModel:
    entity_id: str
    scope_type: str
    scope_id: str | None
    theme_name: str
    density_level: str
    active: bool


@dataclass(frozen=True, slots=True)
class CacheExpirationPolicyRowViewModel:
    entity_id: str
    entity_type: str
    ttl_seconds: int
    active: bool


@dataclass(frozen=True, slots=True)
class OfflineCacheEntryRowViewModel:
    entity_id: str
    entity_type: str
    cached_entity_id: str
    workstation_name: str
    sync_state: str
    cached_at: str


@dataclass(frozen=True, slots=True)
class AuditLogRowViewModel:
    fecha: str
    usuario: str
    modulo: str
    accion: str
    detalle: str


@dataclass(frozen=True, slots=True)
class DeviceProfileOptionViewModel:
    entity_id: str
    name: str
    device_type: str
    connection_type: str


@dataclass(frozen=True, slots=True)
class BranchOptionViewModel:
    entity_id: str
    name: str


@dataclass(frozen=True, slots=True)
class DeviceDetailViewModel:
    entity_id: str
    branch_id: str
    profile_id: str
    code: str
    name: str
    status: str
    notes: str
    blocked_reason: str | None


@dataclass(frozen=True, slots=True)
class DeviceOptionViewModel:
    entity_id: str
    code: str
    name: str
    device_type: str


@dataclass(frozen=True, slots=True)
class PrintRouteRowViewModel:
    entity_id: str
    document_type: str
    primary_device_id: str
    primary_device_code: str
    fallback_device_ids: tuple[str, ...]
    branch_id: str | None
    module: str | None
    channel: str | None
    active: bool


@dataclass(frozen=True, slots=True)
class MarketingCampaignRowViewModel:
    entity_id: str
    code: str
    category: str
    message_template: str
    priority: int
    requires_customer: bool
    rules: tuple
    active: bool


@dataclass(frozen=True, slots=True)
class ContentRowViewModel:
    entity_id: str
    title: str
    content_type: str
    duration_seconds: int
    active: bool


@dataclass(frozen=True, slots=True)
class ContentDetailViewModel:
    entity_id: str
    title: str
    content_type: str
    body: str
    duration_seconds: int


@dataclass(frozen=True, slots=True)
class ContentCampaignRowViewModel:
    entity_id: str
    name: str
    content_title: str
    status: str
    starts_at: str | None
    ends_at: str | None


@dataclass(frozen=True, slots=True)
class AdvertisingSlotRowViewModel:
    entity_id: str
    code: str
    mode: str
    display_order: int
    active: bool


@dataclass(frozen=True, slots=True)
class CampaignPlacementRowViewModel:
    entity_id: str
    campaign_name: str
    slot_code: str
    active: bool
    assigned_at: str


@dataclass(frozen=True, slots=True)
class IntegrationDefinitionRowViewModel:
    entity_id: str
    code: str
    name: str
    category: str
    required_credential_names: tuple[str, ...]
    active: bool


@dataclass(frozen=True, slots=True)
class IntegrationInstanceRowViewModel:
    entity_id: str
    definition_id: str
    name: str
    config: dict
    credential_references: dict
    active: bool


@dataclass(frozen=True, slots=True)
class WebhookEndpointRowViewModel:
    entity_id: str
    instance_id: str
    code: str
    path: str
    signature_scheme: str
    active: bool
    last_received_at: str | None


@dataclass(frozen=True, slots=True)
class IntegrationHealthCheckRowViewModel:
    entity_id: str
    success: bool
    message: str
    checked_at: str


@dataclass(frozen=True, slots=True)
class NotificationAccountRowViewModel:
    entity_id: str
    channel: str
    name: str
    credential_reference: str | None
    active: bool


@dataclass(frozen=True, slots=True)
class NotificationTemplateRowViewModel:
    entity_id: str
    code: str
    channel: str
    language: str
    parameter_names: tuple[str, ...]
    active: bool


@dataclass(frozen=True, slots=True)
class NotificationRouteRowViewModel:
    entity_id: str
    event_code: str
    channel: str
    template_code: str
    account_name: str
    active: bool


@dataclass(frozen=True, slots=True)
class AssignmentRowViewModel:
    entity_id: str
    role: str
    device_id: str
    device_code: str
    device_name: str


@dataclass(frozen=True, slots=True)
class WorkstationDetailViewModel:
    entity_id: str
    branch_id: str
    code: str
    name: str
    workstation_type: str
    device_identifier: str
    operating_system: str
    status: str
    blocked_reason: str | None


@dataclass(frozen=True, slots=True)
class TemplateDetailViewModel:
    entity_id: str
    document_type: str
    name: str
    module: str
    description: str


@dataclass(frozen=True, slots=True)
class TemplateVersionRowViewModel:
    entity_id: str
    template_id: str
    version: int
    status: str
    content: str
    reason: str | None
    created_by_user_id: str | None


@dataclass(frozen=True, slots=True)
class CompanyProfileDetailViewModel:
    entity_id: str
    legal_name: str
    commercial_name: str
    tax_id: str
    business_name: str
    default_currency: str
    default_timezone: str
    default_locale: str
    fiscal_regime_reference: str | None
    address: str
    phone: str | None
    email: str | None
    website: str | None
    logo_asset_id: str | None


@dataclass(frozen=True, slots=True)
class BranchProfileDetailViewModel:
    entity_id: str
    branch_id: str
    code: str
    name: str
    address: str
    phone: str | None
    timezone: str
    locale: str
    opening_time: str | None
    closing_time: str | None
    operation_days: tuple[str, ...]
    ticket_header: str
    ticket_footer: str


class ConfiguracionWorkspaceQueryService:
    def __init__(self, connection, secret_store=None) -> None:
        self._conn = connection
        self._secret_store = secret_store

    def page(self, *, page_id: str, search: str = "") -> ConfigPageViewModel:
        handler = self._HANDLERS.get(page_id)
        if handler is None:
            raise KeyError(f"Unknown Configuración route: {page_id}")
        return handler(self, search)

    # sections ------------------------------------------------------------------
    def _page_empresa(self, search: str) -> ConfigPageViewModel:
        columns = (
            ConfigColumnDTO("Código"), ConfigColumnDTO("Nombre"), ConfigColumnDTO("Horario"),
            ConfigColumnDTO("Activo", "status"),
        )
        branches = SqliteBranchProfileRepository(self._conn).list_active()
        rows = tuple(
            ConfigRowViewModel(b.branch_id, (
                b.code, b.name,
                f"{b.opening_time}–{b.closing_time}" if b.opening_time and b.closing_time else "—",
                "Sí" if b.active else "No",
            ))
            for b in branches
        )
        return self._filtered(columns, rows, search, "No hay sucursales con perfil de gobierno todavía.")

    def _page_general(self, search: str) -> ConfigPageViewModel:
        columns = (
            ConfigColumnDTO("Código"), ConfigColumnDTO("Nombre"), ConfigColumnDTO("Tipo"),
            ConfigColumnDTO("Estado", "status"), ConfigColumnDTO("Última actividad", "date"),
        )
        # Full lifecycle view (not just list_active()) — a management page
        # needs to see and act on blocked/inactive/retired workstations
        # too, not only the currently-active ones (same reasoning as
        # _page_dispositivos).
        workstations = SqliteWorkstationRepository(self._conn).list_all()
        rows = tuple(
            ConfigRowViewModel(w.id, (
                w.code, w.name, w.workstation_type.value, w.status.value, w.last_seen_at or "—",
            ))
            for w in workstations
        )
        return self._filtered(columns, rows, search, "No hay estaciones registradas todavía.")

    def get_workstation(self, workstation_id: str) -> WorkstationDetailViewModel | None:
        workstation = SqliteWorkstationRepository(self._conn).get(workstation_id)
        if workstation is None:
            return None
        return WorkstationDetailViewModel(
            entity_id=workstation.id, branch_id=workstation.branch_id, code=workstation.code,
            name=workstation.name, workstation_type=workstation.workstation_type.value,
            device_identifier=workstation.device_identifier,
            operating_system=workstation.operating_system, status=workstation.status.value,
            blocked_reason=workstation.blocked_reason,
        )

    def _page_dispositivos(self, search: str) -> ConfigPageViewModel:
        columns = (
            ConfigColumnDTO("Código"), ConfigColumnDTO("Nombre"), ConfigColumnDTO("Estado", "status"),
            ConfigColumnDTO("Notas"),
        )
        # Full lifecycle view (not just list_active()) — a management page
        # needs to see and act on blocked/inactive/retired devices too, not
        # only the currently-active ones.
        devices = SqliteDeviceRepository(self._conn).list_all()
        rows = tuple(
            ConfigRowViewModel(d.id, (d.code, d.name, d.status.value, d.notes or "—"))
            for d in devices
        )
        return self._filtered(columns, rows, search, "No hay dispositivos registrados todavía.")

    def _page_documentos(self, search: str) -> ConfigPageViewModel:
        columns = (
            ConfigColumnDTO("Nombre"), ConfigColumnDTO("Tipo de documento"), ConfigColumnDTO("Módulo"),
            ConfigColumnDTO("Activo", "status"),
        )
        # Full lifecycle view (not just list_active()) — same reasoning as
        # _page_dispositivos/_page_general: a management page needs to see
        # and act on inactive templates too, not only active ones.
        templates = SqliteDocumentTemplateRepository(self._conn).list_all()
        rows = tuple(
            ConfigRowViewModel(t.id, (t.name, t.document_type.value, t.module, "Sí" if t.active else "No"))
            for t in templates
        )
        return self._filtered(columns, rows, search, "No hay plantillas de documento todavía.")

    def _page_pantalla_cliente(self, search: str) -> ConfigPageViewModel:
        columns = (
            ConfigColumnDTO("Nombre"), ConfigColumnDTO("Estación"), ConfigColumnDTO("Modo actual", "status"),
        )
        displays = SqliteCustomerDisplayRepository(self._conn).list_active()
        rows = tuple(
            ConfigRowViewModel(d.id, (d.name, d.workstation_id, d.current_mode.value))
            for d in displays
        )
        return self._filtered(columns, rows, search, "No hay pantallas de cliente activas.")

    def _page_integraciones(self, search: str) -> ConfigPageViewModel:
        """SET-19 cutover: the main table now lists `IntegrationDefinition`s
        (the catalog of integration KINDS) — `IntegracionesPage` drives
        Instances/Webhooks/Health as selection-cascaded secondary cards,
        same "select the parent row, load the children" shape
        `documentos_page.py` already established for Templates→Versions."""
        columns = (
            ConfigColumnDTO("Código"), ConfigColumnDTO("Nombre"), ConfigColumnDTO("Categoría"),
            ConfigColumnDTO("Activo", "status"),
        )
        definitions = SqliteIntegrationDefinitionRepository(self._conn).list_active()
        rows = tuple(
            ConfigRowViewModel(d.id, (d.code, d.name, d.category.value, "Sí"))
            for d in definitions
        )
        return self._filtered(columns, rows, search, "No hay definiciones de integración activas.")

    def list_integration_definitions(self) -> tuple[IntegrationDefinitionRowViewModel, ...]:
        definitions = SqliteIntegrationDefinitionRepository(self._conn).list_active()
        return tuple(
            IntegrationDefinitionRowViewModel(
                entity_id=d.id, code=d.code, name=d.name, category=d.category.value,
                required_credential_names=d.required_credential_names, active=d.active,
            )
            for d in definitions
        )

    def list_integration_instances(self, definition_id: str) -> tuple[IntegrationInstanceRowViewModel, ...]:
        instances = SqliteIntegrationInstanceRepository(self._conn).list_by_definition(definition_id)
        return tuple(
            IntegrationInstanceRowViewModel(
                entity_id=i.id, definition_id=i.definition_id, name=i.name, config=i.config,
                credential_references=i.credential_references, active=i.active,
            )
            for i in instances
        )

    def list_webhook_endpoints(self, instance_id: str) -> tuple[WebhookEndpointRowViewModel, ...]:
        endpoints = SqliteWebhookEndpointRepository(self._conn).list_by_instance(instance_id)
        return tuple(
            WebhookEndpointRowViewModel(
                entity_id=e.id, instance_id=e.instance_id, code=e.code, path=e.path,
                signature_scheme=e.signature_scheme.value, active=e.active,
                last_received_at=e.last_received_at,
            )
            for e in endpoints
        )

    def list_integration_health_checks(self, instance_id: str) -> tuple[IntegrationHealthCheckRowViewModel, ...]:
        checks = SqliteIntegrationHealthCheckRepository(self._conn).list_for_instance(instance_id)
        return tuple(
            IntegrationHealthCheckRowViewModel(
                entity_id=c.id, success=c.success, message=c.message, checked_at=c.checked_at,
            )
            for c in checks
        )

    def get_integration_health_status(self, instance_id: str) -> str:
        from backend.domain.integrations.policies.integration_health_policy import current_status

        checks = SqliteIntegrationHealthCheckRepository(self._conn).list_for_instance(instance_id)
        return current_status(checks).value

    def get_credential_status(self, credential_reference: str | None) -> str:
        """UI-safe: only ever calls `describe()`, never `get_secret()` —
        `SecretStoreGateway`'s own docstring says the UI layer must not
        read a raw secret back."""
        if not credential_reference:
            return "No configurada"
        secret_store = self._secret_store
        if secret_store is None:
            from backend.security.secrets.default_secret_store import build_default_secret_store

            secret_store = build_default_secret_store()
        reference = secret_store.describe(credential_reference)
        if reference is None:
            return "No configurada"
        return f"Configurada ({reference.masked_value})"

    def _page_feature_flags(self, search: str) -> ConfigPageViewModel:
        columns = (
            ConfigColumnDTO("Código"), ConfigColumnDTO("Nombre"), ConfigColumnDTO("Default", "status"),
            ConfigColumnDTO("Activo", "status"),
        )
        flags = SqliteFeatureFlagRepository(self._conn).list_all()
        rows = tuple(
            ConfigRowViewModel(
                f.id, (f.code, f.name, "Sí" if f.default_enabled else "No", "Sí" if f.active else "No"))
            for f in flags
        )
        return self._filtered(columns, rows, search, "No hay feature flags todavía.")

    def _page_apariencia(self, search: str) -> ConfigPageViewModel:
        columns = (
            ConfigColumnDTO("Código"), ConfigColumnDTO("Nombre"), ConfigColumnDTO("Modo", "status"),
            ConfigColumnDTO("Predeterminado", "status"), ConfigColumnDTO("Activo", "status"),
        )
        themes = SqliteThemeRepository(self._conn).list_all()
        rows = tuple(
            ConfigRowViewModel(
                t.id,
                (t.code, t.name, t.mode.value, "Sí" if t.is_default else "No", "Sí" if t.active else "No"))
            for t in themes
        )
        return self._filtered(columns, rows, search, "No hay temas todavía.")

    def _page_notificaciones(self, search: str) -> ConfigPageViewModel:
        columns = (
            ConfigColumnDTO("Evento"), ConfigColumnDTO("Canal", "status"), ConfigColumnDTO("Activo", "status"),
        )
        routes = SqliteNotificationRouteRepository(self._conn).list_active()
        rows = tuple(
            ConfigRowViewModel(r.id, (r.event_code, r.channel.value, "Sí"))
            for r in routes
        )
        return self._filtered(columns, rows, search, "No hay rutas de notificación activas.")

    def list_notification_accounts(self) -> tuple[NotificationAccountRowViewModel, ...]:
        accounts = SqliteNotificationAccountRepository(self._conn).list_active()
        return tuple(
            NotificationAccountRowViewModel(
                entity_id=a.id, channel=a.channel.value, name=a.name,
                credential_reference=a.credential_reference, active=a.active,
            )
            for a in accounts
        )

    def list_notification_templates(self) -> tuple[NotificationTemplateRowViewModel, ...]:
        templates = SqliteNotificationTemplateRepository(self._conn).list_active()
        return tuple(
            NotificationTemplateRowViewModel(
                entity_id=t.id, code=t.code, channel=t.channel.value, language=t.language,
                parameter_names=t.parameter_names, active=t.active,
            )
            for t in templates
        )

    def list_notification_routes(self) -> tuple[NotificationRouteRowViewModel, ...]:
        template_repo = SqliteNotificationTemplateRepository(self._conn)
        account_repo = SqliteNotificationAccountRepository(self._conn)
        routes = SqliteNotificationRouteRepository(self._conn).list_active()
        rows = []
        for r in routes:
            template = template_repo.get(r.template_id)
            account = account_repo.get(r.account_id)
            rows.append(NotificationRouteRowViewModel(
                entity_id=r.id, event_code=r.event_code, channel=r.channel.value,
                template_code=template.code if template else r.template_id,
                account_name=account.name if account else r.account_id, active=r.active,
            ))
        return tuple(rows)

    def _page_offline(self, search: str) -> ConfigPageViewModel:
        columns = (
            ConfigColumnDTO("Tipo de entidad"), ConfigColumnDTO("TTL (segundos)", "numeric"),
            ConfigColumnDTO("Activo", "status"),
        )
        policies = SqliteCacheExpirationPolicyRepository(self._conn).list_all()
        rows = tuple(
            ConfigRowViewModel(p.id, (p.entity_type, str(p.ttl_seconds), "Sí" if p.active else "No"))
            for p in policies
        )
        return self._filtered(columns, rows, search, "No hay políticas de expiración de caché todavía.")

    def _page_usuarios_roles(self, search: str) -> ConfigPageViewModel:
        columns = (
            ConfigColumnDTO("Usuario"), ConfigColumnDTO("Nombre"), ConfigColumnDTO("Rol"),
            ConfigColumnDTO("Sucursal"), ConfigColumnDTO("Estado", "status"),
            ConfigColumnDTO("Seguridad", "status"),
        )
        users = self._user_management_service().list_users()
        rows = tuple(
            ConfigRowViewModel(u.id, (
                u.username, u.name, u.role, u.branch_name, "Activo" if u.active else "Inactivo",
                f"Bloqueado hasta {u.locked_until}" if u.locked_until
                else (f"{u.failed_attempts} intentos fallidos" if u.failed_attempts else "Sin bloqueos"),
            ))
            for u in users
        )
        return self._filtered(columns, rows, search, "No hay usuarios todavía.")

    def list_cache_expiration_policies(self) -> tuple[CacheExpirationPolicyRowViewModel, ...]:
        policies = SqliteCacheExpirationPolicyRepository(self._conn).list_all()
        return tuple(
            CacheExpirationPolicyRowViewModel(
                entity_id=p.id, entity_type=p.entity_type, ttl_seconds=p.ttl_seconds, active=p.active,
            )
            for p in policies
        )

    def list_offline_cache_entries(self) -> tuple[OfflineCacheEntryRowViewModel, ...]:
        workstation_repo = SqliteWorkstationRepository(self._conn)
        entries = SqliteOfflineCacheEntryRepository(self._conn).list_all()
        rows = []
        for e in entries:
            workstation = workstation_repo.get(e.workstation_id)
            rows.append(OfflineCacheEntryRowViewModel(
                entity_id=e.id, entity_type=e.entity_type, cached_entity_id=e.entity_id,
                workstation_name=workstation.name if workstation else e.workstation_id,
                sync_state=e.sync_state.value, cached_at=e.cached_at,
            ))
        return tuple(rows)

    # Usuarios/Roles/Auditoría — thin passthroughs to the already-canonical
    # "FASE 6" application-service layer (core/services/
    # configuracion_settings_service.py), never re-implemented here.
    def _user_management_service(self):
        from repositories.config_repository import ConfigRepository
        from core.services.configuration_settings_service import UserManagementService

        return UserManagementService(ConfigRepository(self._conn))

    def _role_management_service(self):
        from repositories.config_repository import ConfigRepository
        from core.services.configuration_settings_service import RoleManagementService

        return RoleManagementService(ConfigRepository(self._conn))

    def _permission_query_service(self):
        from repositories.config_repository import ConfigRepository
        from core.services.configuration_settings_service import PermissionQueryService

        return PermissionQueryService(ConfigRepository(self._conn))

    def _company_profile_service(self):
        from repositories.config_repository import ConfigRepository
        from core.services.configuration_settings_service import CompanyProfileService

        return CompanyProfileService(ConfigRepository(self._conn))

    def list_users(self) -> tuple[UserSettingsDTO, ...]:
        return tuple(self._user_management_service().list_users())

    def get_user_form_data(self, user_id: str) -> UserSettingsDTO | None:
        return self._user_management_service().get_user_form_data(user_id)

    def list_roles(self) -> tuple[RoleSettingsDTO, ...]:
        return tuple(self._role_management_service().list_roles())

    def list_role_names(self) -> tuple[str, ...]:
        return tuple(self._role_management_service().role_names())

    def list_branches_for_user_selector(self) -> tuple[tuple[str, str], ...]:
        return tuple(self._role_management_service().active_branches_for_selector())

    def list_employees_for_user_selector(self) -> tuple[tuple[str, str], ...]:
        return tuple(self._role_management_service().active_employees_for_selector())

    def get_installation_branch(self) -> tuple[str, str] | None:
        return self._company_profile_service().get_installation_branch()

    def audit_log_rows(self, limit: int = 200) -> tuple[AuditLogRowViewModel, ...]:
        rows = self._permission_query_service().audit_log_rows(limit)
        return tuple(
            AuditLogRowViewModel(fecha=str(r[0] or ""), usuario=str(r[1] or ""), modulo=str(r[2] or ""),
                                  accion=str(r[3] or ""), detalle=str(r[4] or ""))
            for r in rows
        )

    # write-flow support ----------------------------------------------------------
    def list_feature_flags(self) -> tuple[FeatureFlagRowViewModel, ...]:
        flags = SqliteFeatureFlagRepository(self._conn).list_all()
        return tuple(
            FeatureFlagRowViewModel(
                entity_id=f.id, code=f.code, name=f.name, description=f.description,
                default_enabled=f.default_enabled, active=f.active,
            )
            for f in flags
        )

    def list_feature_flag_rules(self, flag_id: str) -> tuple[FeatureFlagRuleRowViewModel, ...]:
        rules = SqliteFeatureFlagRuleRepository(self._conn).list_for_flag(flag_id)
        return tuple(
            FeatureFlagRuleRowViewModel(
                entity_id=r.id, scope_type=r.scope_type.value, scope_id=r.scope_id, enabled=r.enabled,
                rollout_percentage=r.rollout_percentage, active=r.active,
            )
            for r in rules
        )

    def list_pending_feature_flag_change_requests(self) -> tuple[ChangeRequestRowViewModel, ...]:
        flag_repo = SqliteFeatureFlagRepository(self._conn)
        requests = SqliteFeatureFlagChangeRequestRepository(self._conn).list_pending()
        rows = []
        for request in requests:
            flag = flag_repo.get(request.flag_id)
            scope = request.scope_type.value if request.scope_id is None else (
                f"{request.scope_type.value} ({request.scope_id})"
            )
            rows.append(ChangeRequestRowViewModel(
                entity_id=request.id, flag_code=flag.code if flag else request.flag_id, scope=scope,
                proposed_enabled="Sí" if request.proposed_enabled else "No",
                requested_by=request.requested_by_user_id,
            ))
        return tuple(rows)

    def list_themes(self) -> tuple[ThemeRowViewModel, ...]:
        themes = SqliteThemeRepository(self._conn).list_all()
        return tuple(
            ThemeRowViewModel(t.id, t.code, t.name, t.mode.value, t.is_default) for t in themes
        )

    def list_light_dark_theme_codes(self) -> tuple[str, str]:
        """Convenience for dialogs that only need to show the two `ThemeMode`
        options — never invents a third mode locally."""
        return ThemeMode.LIGHT.value, ThemeMode.DARK.value

    def list_design_tokens_for_theme(self, theme_id: str) -> tuple[DesignTokenRowViewModel, ...]:
        tokens = SqliteDesignTokenRepository(self._conn).list_for_theme(theme_id)
        return tuple(
            DesignTokenRowViewModel(
                entity_id=t.id, theme_id=t.theme_id, token_key=t.token_key, category=t.category.value,
                token_value=t.token_value,
            )
            for t in tokens
        )

    def list_density_profiles(self) -> tuple[DensityProfileRowViewModel, ...]:
        profiles = SqliteDensityProfileRepository(self._conn).list_all()
        return tuple(
            DensityProfileRowViewModel(
                entity_id=p.id, level=p.level.value, name=p.name, scale_factor=str(p.scale_factor),
                control_height_px=p.control_height_px, touch_target_px=p.touch_target_px,
                spacing_unit_px=p.spacing_unit_px, active=p.active,
            )
            for p in profiles
        )

    def list_appearance_preferences(self) -> tuple[AppearancePreferenceRowViewModel, ...]:
        theme_repo = SqliteThemeRepository(self._conn)
        preferences = SqliteAppearancePreferenceRepository(self._conn).list_all()
        rows = []
        for p in preferences:
            theme = theme_repo.get(p.theme_id)
            rows.append(AppearancePreferenceRowViewModel(
                entity_id=p.id, scope_type=p.scope_type.value, scope_id=p.scope_id,
                theme_name=theme.name if theme else p.theme_id, density_level=p.density_level.value,
                active=p.active,
            ))
        return tuple(rows)

    def list_device_profiles(self) -> tuple[DeviceProfileOptionViewModel, ...]:
        profiles = SqliteDeviceProfileRepository(self._conn).list_active()
        return tuple(
            DeviceProfileOptionViewModel(
                p.id, p.name, p.device_type.value, p.connection_profile.connection_type.value,
            )
            for p in profiles
        )

    def list_devices(self) -> tuple[DeviceOptionViewModel, ...]:
        devices = SqliteDeviceRepository(self._conn).list_active()
        profile_repo = SqliteDeviceProfileRepository(self._conn)
        rows = []
        for d in devices:
            profile = profile_repo.get(d.profile_id)
            device_type = profile.device_type.value if profile else ""
            rows.append(DeviceOptionViewModel(d.id, d.code, d.name, device_type))
        return tuple(rows)

    def list_workstation_assignments(self, workstation_id: str) -> tuple[AssignmentRowViewModel, ...]:
        assignments = SqliteWorkstationDeviceAssignmentRepository(self._conn).list_active_for_workstation(
            workstation_id,
        )
        device_repo = SqliteDeviceRepository(self._conn)
        rows = []
        for a in assignments:
            device = device_repo.get(a.device_id)
            rows.append(AssignmentRowViewModel(
                entity_id=a.id, role=a.role.value, device_id=a.device_id,
                device_code=device.code if device else "—", device_name=device.name if device else "—",
            ))
        return tuple(rows)

    def list_print_routes(self) -> tuple[PrintRouteRowViewModel, ...]:
        routes = SqlitePrintRouteRepository(self._conn).list_all()
        device_repo = SqliteDeviceRepository(self._conn)
        rows = []
        for r in routes:
            primary = device_repo.get(r.primary_device_id)
            rows.append(PrintRouteRowViewModel(
                entity_id=r.id, document_type=r.document_type, primary_device_id=r.primary_device_id,
                primary_device_code=primary.code if primary else "—",
                fallback_device_ids=r.fallback_device_ids, branch_id=r.branch_id, module=r.module,
                channel=r.channel, active=r.active,
            ))
        return tuple(rows)

    def list_marketing_campaigns(self) -> tuple[MarketingCampaignRowViewModel, ...]:
        campaigns = SqliteMarketingCampaignRepository(self._conn).list_all()
        return tuple(
            MarketingCampaignRowViewModel(
                entity_id=c.id, code=c.code, category=c.category.value,
                message_template=c.message_template, priority=c.priority,
                requires_customer=c.requires_customer, rules=c.rules, active=c.active,
            )
            for c in campaigns
        )

    def get_display_content(self, content_id: str) -> ContentDetailViewModel | None:
        content = SqliteContentRepository(self._conn).get(content_id)
        if content is None:
            return None
        return ContentDetailViewModel(
            entity_id=content.id, title=content.title, content_type=content.content_type.value,
            body=content.body, duration_seconds=content.duration_seconds,
        )

    def list_display_content(self) -> tuple[ContentRowViewModel, ...]:
        items = SqliteContentRepository(self._conn).list_all()
        return tuple(
            ContentRowViewModel(
                entity_id=c.id, title=c.title, content_type=c.content_type.value,
                duration_seconds=c.duration_seconds, active=c.active,
            )
            for c in items
        )

    def list_content_campaigns(self) -> tuple[ContentCampaignRowViewModel, ...]:
        content_repo = SqliteContentRepository(self._conn)
        campaigns = SqliteContentCampaignRepository(self._conn).list_all()
        rows = []
        for c in campaigns:
            content = content_repo.get(c.content_id)
            rows.append(ContentCampaignRowViewModel(
                entity_id=c.id, name=c.name, content_title=content.title if content else c.content_id,
                status=c.status.value, starts_at=c.starts_at, ends_at=c.ends_at,
            ))
        return tuple(rows)

    def list_advertising_slots(self) -> tuple[AdvertisingSlotRowViewModel, ...]:
        slots = SqliteAdvertisingSlotRepository(self._conn).list_all()
        return tuple(
            AdvertisingSlotRowViewModel(
                entity_id=s.id, code=s.code, mode=s.mode.value, display_order=s.display_order,
                active=s.active,
            )
            for s in slots
        )

    def list_campaign_placements(self) -> tuple[CampaignPlacementRowViewModel, ...]:
        campaign_repo = SqliteContentCampaignRepository(self._conn)
        slot_repo = SqliteAdvertisingSlotRepository(self._conn)
        placements = SqliteCampaignPlacementRepository(self._conn).list_all()
        rows = []
        for p in placements:
            campaign = campaign_repo.get(p.campaign_id)
            slot = slot_repo.get(p.slot_id)
            rows.append(CampaignPlacementRowViewModel(
                entity_id=p.id, campaign_name=campaign.name if campaign else p.campaign_id,
                slot_code=slot.code if slot else p.slot_id, active=p.active, assigned_at=p.assigned_at,
            ))
        return tuple(rows)

    def get_impression_summary(self, placement_id: str) -> str:
        impressions = SqliteContentImpressionRepository(self._conn).list_for_placement(placement_id)
        summary = summarize_impressions(impressions)
        return (
            f"Impresiones: {summary.total_impressions}\n"
            f"Duración total: {summary.total_duration_seconds}s\n"
            f"Duración promedio: {summary.average_duration_seconds}s"
        )

    def list_branches(self) -> tuple[BranchOptionViewModel, ...]:
        rows = self._conn.execute(
            "SELECT id, nombre FROM sucursales WHERE activa=1 ORDER BY nombre",
        ).fetchall()
        return tuple(BranchOptionViewModel(row[0], row[1]) for row in rows)

    def get_template(self, template_id: str) -> TemplateDetailViewModel | None:
        template = SqliteDocumentTemplateRepository(self._conn).get(template_id)
        if template is None:
            return None
        return TemplateDetailViewModel(
            entity_id=template.id, document_type=template.document_type.value, name=template.name,
            module=template.module, description=template.description,
        )

    def list_template_versions(self, template_id: str) -> tuple[TemplateVersionRowViewModel, ...]:
        versions = SqliteDocumentTemplateVersionRepository(self._conn).list_for_template(template_id)
        return tuple(
            TemplateVersionRowViewModel(
                entity_id=v.id, template_id=v.template_id, version=v.version, status=v.status.value,
                content=v.content, reason=v.reason, created_by_user_id=v.created_by_user_id,
            )
            for v in versions
        )

    def get_device(self, device_id: str) -> DeviceDetailViewModel | None:
        device = SqliteDeviceRepository(self._conn).get(device_id)
        if device is None:
            return None
        return DeviceDetailViewModel(
            entity_id=device.id, branch_id=device.branch_id, profile_id=device.profile_id,
            code=device.code, name=device.name, status=device.status.value, notes=device.notes,
            blocked_reason=device.blocked_reason,
        )

    def get_company_profile(self) -> CompanyProfileDetailViewModel | None:
        companies = SqliteCompanyProfileRepository(self._conn).list_active()
        if not companies:
            return None
        company = companies[0]
        return CompanyProfileDetailViewModel(
            entity_id=company.id, legal_name=company.legal_name, commercial_name=company.commercial_name,
            tax_id=company.tax_id, business_name=company.business_name,
            default_currency=company.default_currency, default_timezone=company.default_timezone,
            default_locale=company.default_locale, fiscal_regime_reference=company.fiscal_regime_reference,
            address=company.address, phone=company.phone, email=company.email, website=company.website,
            logo_asset_id=company.logo_asset.asset_id if company.logo_asset else None,
        )

    def get_branch_profile(self, branch_id: str) -> BranchProfileDetailViewModel | None:
        branch = SqliteBranchProfileRepository(self._conn).get(branch_id)
        if branch is None:
            return None
        return BranchProfileDetailViewModel(
            entity_id=branch.id, branch_id=branch.branch_id, code=branch.code, name=branch.name,
            address=branch.address, phone=branch.phone, timezone=branch.timezone, locale=branch.locale,
            opening_time=branch.opening_time.isoformat() if branch.opening_time else None,
            closing_time=branch.closing_time.isoformat() if branch.closing_time else None,
            operation_days=branch.operation_days, ticket_header=branch.ticket_header,
            ticket_footer=branch.ticket_footer,
        )

    def list_unregistered_branches(self) -> tuple[BranchOptionViewModel, ...]:
        """`sucursales` rows that don't have a `BranchProfile` governance
        record yet — the candidate list for "Nueva sucursal" (registering
        a profile, never creating a new physical branch — see
        `RegisterBranchProfileUseCase`'s own docstring)."""
        rows = self._conn.execute(
            "SELECT id, nombre FROM sucursales WHERE activa=1 AND id NOT IN"
            " (SELECT branch_id FROM branch_profiles) ORDER BY nombre",
        ).fetchall()
        return tuple(BranchOptionViewModel(row[0], row[1]) for row in rows)

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _filtered(
        columns: tuple[ConfigColumnDTO, ...], rows: tuple[ConfigRowViewModel, ...], search: str,
        empty_message: str,
    ) -> ConfigPageViewModel:
        term = search.strip().lower()
        if term:
            rows = tuple(row for row in rows if any(term in cell.lower() for cell in row.cells))
        return ConfigPageViewModel(columns=columns, rows=rows, empty_message=empty_message)

    _HANDLERS = {
        "config_empresa": _page_empresa,
        "config_general": _page_general,
        "config_dispositivos": _page_dispositivos,
        "config_documentos": _page_documentos,
        "config_pantalla_cliente": _page_pantalla_cliente,
        "config_integraciones": _page_integraciones,
        "config_feature_flags": _page_feature_flags,
        "config_apariencia": _page_apariencia,
        "config_notificaciones": _page_notificaciones,
        "config_offline": _page_offline,
        "config_usuarios_roles": _page_usuarios_roles,
    }
