"""Save role use case — single canonical route for creating/updating a
role's identity (name/description). Distinct from
`SaveRolePermissionsUseCase`, which manages a role's permission matrix,
not its identity."""

from __future__ import annotations

from backend.application.configuracion.authorization import ConfiguracionAuthorizationPolicy
from backend.application.configuracion.permissions import ConfiguracionPermissions
from backend.application.commands.settings_commands import SaveRoleCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.security.unwired_policy import unwired
from backend.application.use_cases.base_use_case import BaseUseCase


class SaveRoleUseCase(BaseUseCase[SaveRoleCommand]):
    name = "SaveRoleUseCase"

    def __init__(self, role_management_service, authorization=None) -> None:
        self._service = role_management_service
        # Auditoría de permisos 968e0bc: el permiso se revalida AQUÍ y no sólo
        # en la pantalla. Sin política cableada, falla cerrada.
        self._auth = authorization or unwired(ConfiguracionAuthorizationPolicy)

    def execute(self, command: SaveRoleCommand) -> UseCaseResult:
        command.validate_context()
        self._auth.require(str(command.user_name or ""), (
            ConfiguracionPermissions.ROLES_EDITAR if command.role_id
            else ConfiguracionPermissions.ROLES_CREAR))
        role_id = self._service.save_role(
            role_id=command.role_id or None,
            name=command.name,
            description=command.description,
            operation_id=command.operation_id,
            actor=command.user_name or "",
        )
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=role_id)
