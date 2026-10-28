"""ApplicationContextBuilder — SHELL-7.

Convierte un login correcto (`AuthenticateUserUseCase`) en un
`ApplicationContext` real (SHELL-6): quién es, desde dónde, con qué permisos y
con qué capacidades encendidas.

El bootstrap no habla SQL (§12). Cada dato lo pide a la pieza que ya es dueña
de esa pregunta:

    permisos      -> PermissionQueryService  (backend/application/security/)
    capacidades   -> BranchFeatureFlagsQuery (backend/application/feature_flags/)
    instalación   -> SqliteInstallationRepository
    sucursal      -> SqliteBranchDirectoryRepository

Los repositorios se construyen aquí, en el momento de armar el contexto, y no
en `__init__`: `build()` es la composición de un contexto de sesión, y crear
adaptadores antes de que haya sesión sólo los dejaría esperando.

SITIO DE LA SESIÓN (auditoría enterprise, Fase 2; N01) — la sesión opera el sitio
anclado a ESTA estación (`sucursal_instalacion_id`), no la sucursal propia del
usuario: antes un cajero de otra sucursal que entraba en esta caja vendía el
inventario de la suya. Sólo sin ancla se usa la sucursal propia. El usuario
necesita un rol cuyo ámbito cubra el sitio (`AccessScopeResolver`); si no, el
inicio de sesión se rechaza (`SiteAccessDeniedError`). Los permisos y los roles
son los que valen EN ese sitio, el alcance (`assigned_branch_ids`) son todos los
sitios que cubren sus roles (toda la empresa si alguno es de toda la empresa) y
`site_capabilities` son las capacidades de la unidad (POS, CAJA, …).
"""
from __future__ import annotations

from backend.application.feature_flags.branch_feature_flags_query import (
    BranchFeatureFlagsQuery,
)
from backend.application.security.access_scope import AccessScopeResolver
from backend.application.security.permission_query_service import PermissionQueryService
from backend.bootstrap.application_context_errors import SiteAccessDeniedError
from backend.application.software_updates.installation import enabled_capabilities_for
from backend.bootstrap.application_context import (
    ApplicationContext,
    FeatureContext,
    default_workstation_id,
)
from backend.infrastructure.db.repositories.feature_flags.feature_flag_repository import (
    SqliteFeatureFlagRepository,
)
from backend.infrastructure.db.repositories.feature_flags.feature_flag_rule_repository import (
    SqliteFeatureFlagRuleRepository,
)
from backend.infrastructure.db.repositories.organization.org_unit_repository import (
    SqliteOrgUnitRepository,
)
from backend.infrastructure.db.repositories.security.permission_repository import (
    SqlitePermissionRepository,
)
from backend.infrastructure.db.repositories.settings.branch_directory_repository import (
    SqliteBranchDirectoryRepository,
)
from backend.infrastructure.db.repositories.settings.installation_branch_repository import (
    SqliteInstallationBranchRepository,
)
from backend.security.authentication.authenticate_user_use_case import AuthenticationResult
from backend.security.provisioning.installation_repository import SqliteInstallationRepository
from backend.shared.app_paths import AppPaths


class ApplicationContextBuilder:
    def __init__(self, conn) -> None:
        self._conn = conn

    def build(
        self, auth_result: AuthenticationResult, *, workstation_type: str = "",
    ) -> ApplicationContext:
        credentials = auth_result.credentials
        session = auth_result.session

        installation = SqliteInstallationRepository(self._conn).get()
        branches = SqliteBranchDirectoryRepository(self._conn)
        permission_repo = SqlitePermissionRepository(self._conn)
        resolver = AccessScopeResolver(permission_repo)

        site_id, site_name = self._session_site(credentials, branches)
        if site_id and resolver.supports_scopes and not resolver.covers(credentials.id, site_id):
            raise SiteAccessDeniedError(site_name or site_id)

        query = PermissionQueryService(permission_repo)
        permissions = query.permission_codes_for_user(credentials.id, site_id)
        roles = query.roles_for(credentials.id, site_id) or (credentials.role,)

        flags = BranchFeatureFlagsQuery(
            SqliteFeatureFlagRepository(self._conn),
            SqliteFeatureFlagRuleRepository(self._conn),
        ).flags_for(site_id, user_id=credentials.id)

        # Alcance: todos los sitios que cubren sus roles. Antes eran sólo las
        # filas de `usuarios_sucursales`; ahora también la herencia por jerarquía
        # (un rol en una región alcanza sus sucursales) y los roles de toda la
        # empresa (todas las sucursales activas).
        if resolver.supports_scopes:
            reach = resolver.reach(credentials.id)
            assigned = (permission_repo.active_site_ids() if reach.company_wide
                        else reach.site_ids)
        else:
            assigned = frozenset(branches.assigned_branch_ids(credentials.id))

        return ApplicationContext(
            installation_id=installation.id if installation else "",
            company_id=(installation.company_id or "") if installation else "",
            branch_id=site_id,
            branch_name=site_name,
            assigned_branch_ids=frozenset(assigned),
            site_capabilities=self._site_capabilities(site_id),
            workstation_id=session.workstation_id or default_workstation_id(),
            workstation_type=workstation_type,
            user_id=credentials.id,
            user_name=credentials.full_name or credentials.username,
            roles=tuple(roles),
            permissions=frozenset(permissions),
            feature_context=FeatureContext.from_flags_dict(flags),
            session_id=session.session_id,
            capabilities=enabled_capabilities_for(AppPaths.from_environment()),
        )

    def _session_site(self, credentials, branches) -> tuple[str, str]:
        """El sitio anclado a esta estación; sin ancla, la sucursal propia."""
        ancla = SqliteInstallationBranchRepository(self._conn).get()
        if ancla:
            return str(ancla[0]), str(ancla[1] or "")
        propia = str(credentials.branch_id or "")
        return propia, branches.name_for(propia)

    def _site_capabilities(self, site_id: str) -> frozenset[str] | None:
        """Capacidades de la unidad del sitio. `None` (no restringe) si la base no
        tiene estructura organizacional o el sitio no tiene unidad."""
        return SqliteOrgUnitRepository(self._conn).site_capabilities(site_id)
