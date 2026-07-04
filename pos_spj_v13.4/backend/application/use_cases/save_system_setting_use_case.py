"""Save system setting use case — single canonical route."""

from __future__ import annotations

from backend.application.commands.settings_commands import SaveSystemSettingCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase


class SaveSystemSettingUseCase(BaseUseCase[SaveSystemSettingCommand]):
    name = "SaveSystemSettingUseCase"

    def __init__(self, system_settings_service) -> None:
        self._service = system_settings_service

    def execute(self, command: SaveSystemSettingCommand) -> UseCaseResult:
        command.validate_context()
        self._service.set_setting(command.key, command.value)
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=command.key)
