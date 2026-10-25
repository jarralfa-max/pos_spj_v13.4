"""Set user active use case — single canonical route."""

from __future__ import annotations

from backend.application.configuracion.authorization import ConfiguracionAuthorizationPolicy
from backend.application.configuracion.permissions import ConfiguracionPermissions
from backend.application.commands.settings_commands import SetUserActiveCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.security.unwired_policy import unwired
from backend.application.use_cases.base_use_case import BaseUseCase


class SetUserActiveUseCase(BaseUseCase[SetUserActiveCommand]):
    name = "SetUserActiveUseCase"

    def __init__(self, user_management_service, authorization=None) -> None:
        self._service = user_management_service
        # Auditoría de permisos 968e0bc: el permiso se revalida AQUÍ y no sólo
        # en la pantalla. Sin política cableada, falla cerrada.
        self._auth = authorization or unwired(ConfiguracionAuthorizationPolicy)

    def execute(self, command: SetUserActiveCommand) -> UseCaseResult:
        command.validate_context()
        self._auth.require(str(command.user_name or ""), ConfiguracionPermissions.USUARIOS_ACTIVAR)
        self._service.set_user_active(
            command.user_id,
            command.active,
            operation_id=command.operation_id,
            actor=command.user_name or "",
        )
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=command.user_id)
