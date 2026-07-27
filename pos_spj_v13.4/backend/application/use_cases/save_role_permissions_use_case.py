"""Save role permissions use case — single canonical route."""

from __future__ import annotations

from backend.application.commands.settings_commands import SaveRolePermissionsCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase


class SaveRolePermissionsUseCase(BaseUseCase[SaveRolePermissionsCommand]):
    name = "SaveRolePermissionsUseCase"

    def __init__(self, module_access_service) -> None:
        self._service = module_access_service

    def execute(self, command: SaveRolePermissionsCommand) -> UseCaseResult:
        command.validate_context()
        permissions = {
            (str(p["module"]), str(p["action"])): bool(p.get("allowed", p.get("permitido", False)))
            for p in command.permissions
        }
        self._service.save_role_permissions(
            command.role_id,
            permissions,
            operation_id=command.operation_id,
            actor=command.user_name or "",
        )
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=command.role_id)
