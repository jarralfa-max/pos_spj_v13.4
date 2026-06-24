"""Set user active use case — single canonical route."""

from __future__ import annotations

from backend.application.commands.settings_commands import SetUserActiveCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase


class SetUserActiveUseCase(BaseUseCase[SetUserActiveCommand]):
    name = "SetUserActiveUseCase"

    def __init__(self, user_management_service) -> None:
        self._service = user_management_service

    def execute(self, command: SetUserActiveCommand) -> UseCaseResult:
        command.validate_context()
        self._service.set_user_active(
            command.user_id,
            command.active,
            operation_id=command.operation_id,
            actor=command.user_name or "",
        )
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=command.user_id)
