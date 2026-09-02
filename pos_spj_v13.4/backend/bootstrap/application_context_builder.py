"""ApplicationContextBuilder — SHELL-7.

Turns a successful `AuthenticateUserUseCase` result into a real
`ApplicationContext` (SHELL-6), reusing the *existing*
`PermissionQueryService` (reads `rol_permisos`) and `FeatureFlagService`
(reads `feature_flags`) — the same services the legacy app already uses —
instead of building a second, parallel way to load permissions/flags.
"""
from __future__ import annotations

from backend.bootstrap.application_context import ApplicationContext, FeatureContext, default_workstation_id
from backend.security.authentication.authenticate_user_use_case import AuthenticationResult
from backend.security.provisioning.installation_repository import SqliteInstallationRepository


class ApplicationContextBuilder:
    def __init__(self, conn) -> None:
        self._conn = conn

    def build(self, auth_result: AuthenticationResult, *, workstation_type: str = "") -> ApplicationContext:
        from core.services.configuration_settings_service import PermissionQueryService
        from core.services.feature_flag_service import FeatureFlagService
        from repositories.config_repository import ConfigRepository
        from repositories.feature_flag_repository import FeatureFlagRepository

        credentials = auth_result.credentials
        session = auth_result.session

        installation = SqliteInstallationRepository(self._conn).get()
        installation_id = installation.id if installation else ""
        company_id = (installation.company_id or "") if installation else ""

        branch_row = self._conn.execute(
            "SELECT nombre FROM sucursales WHERE id = ?", (credentials.branch_id,),
        ).fetchone()
        branch_name = (branch_row[0] if branch_row else "") or ""

        permissions = PermissionQueryService(ConfigRepository(self._conn)).permission_codes_for_user(
            credentials.id, credentials.branch_id,
        )
        flags = FeatureFlagService(FeatureFlagRepository(self._conn)).get_branch_flags(credentials.branch_id)

        return ApplicationContext(
            installation_id=installation_id,
            company_id=company_id,
            branch_id=credentials.branch_id,
            branch_name=branch_name,
            workstation_id=session.workstation_id or default_workstation_id(),
            workstation_type=workstation_type,
            user_id=credentials.id,
            user_name=credentials.full_name or credentials.username,
            roles=(credentials.role,),
            permissions=frozenset(permissions),
            feature_context=FeatureContext.from_flags_dict(flags),
            session_id=session.session_id,
        )
