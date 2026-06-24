"""Save module toggle use case — single canonical route."""

from __future__ import annotations

from backend.application.commands.settings_commands import SaveModuleToggleCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase


class SaveModuleToggleUseCase(BaseUseCase[SaveModuleToggleCommand]):
    name = "SaveModuleToggleUseCase"

    def __init__(self, module_settings_service) -> None:
        self._service = module_settings_service

    def execute(self, command: SaveModuleToggleCommand) -> UseCaseResult:
        command.validate_context()
        self._service.set_enabled(command.key, command.enabled)
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=command.key)
