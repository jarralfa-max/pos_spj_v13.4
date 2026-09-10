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
"""
from __future__ import annotations

from backend.application.feature_flags.branch_feature_flags_query import (
    BranchFeatureFlagsQuery,
)
from backend.application.security.permission_query_service import PermissionQueryService
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
from backend.infrastructure.db.repositories.security.permission_repository import (
    SqlitePermissionRepository,
)
from backend.infrastructure.db.repositories.settings.branch_directory_repository import (
    SqliteBranchDirectoryRepository,
)
from backend.security.authentication.authenticate_user_use_case import AuthenticationResult
from backend.security.provisioning.installation_repository import SqliteInstallationRepository


class ApplicationContextBuilder:
    def __init__(self, conn) -> None:
        self._conn = conn

    def build(
        self, auth_result: AuthenticationResult, *, workstation_type: str = "",
    ) -> ApplicationContext:
        credentials = auth_result.credentials
        session = auth_result.session

        installation = SqliteInstallationRepository(self._conn).get()

        permissions = PermissionQueryService(
            SqlitePermissionRepository(self._conn)
        ).permission_codes_for_user(credentials.id, credentials.branch_id)

        flags = BranchFeatureFlagsQuery(
            SqliteFeatureFlagRepository(self._conn),
            SqliteFeatureFlagRuleRepository(self._conn),
        ).flags_for(credentials.branch_id, user_id=credentials.id)

        return ApplicationContext(
            installation_id=installation.id if installation else "",
            company_id=(installation.company_id or "") if installation else "",
            branch_id=credentials.branch_id,
            branch_name=SqliteBranchDirectoryRepository(self._conn).name_for(
                credentials.branch_id),
            workstation_id=session.workstation_id or default_workstation_id(),
            workstation_type=workstation_type,
            user_id=credentials.id,
            user_name=credentials.full_name or credentials.username,
            roles=(credentials.role,),
            permissions=frozenset(permissions),
            feature_context=FeatureContext.from_flags_dict(flags),
            session_id=session.session_id,
        )
