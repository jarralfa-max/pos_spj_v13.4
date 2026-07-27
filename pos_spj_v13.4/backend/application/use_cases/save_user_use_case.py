"""Save user use case — single canonical route for creating/updating a user."""

from __future__ import annotations

from backend.application.commands.settings_commands import SaveUserCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase


class SaveUserUseCase(BaseUseCase[SaveUserCommand]):
    name = "SaveUserUseCase"

    def __init__(self, user_management_service) -> None:
        self._service = user_management_service

    def execute(self, command: SaveUserCommand) -> UseCaseResult:
        command.validate_context()
        user_id = self._service.save_user(
            user_id=command.user_id or None,
            username=command.username,
            name=command.full_name,
            email=command.email,
            role=command.role or command.role_id,
            branch_id=command.branch_id,
            active=command.active,
            employee_id=command.employee_id or None,
            password_hash=command.password_hash or None,
            operation_id=command.operation_id,
            actor=command.user_name or "",
        )
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=user_id)
