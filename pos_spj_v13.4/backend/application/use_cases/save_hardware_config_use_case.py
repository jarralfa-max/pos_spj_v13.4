"""Save hardware config use case — single canonical route."""

from __future__ import annotations

from backend.application.commands.settings_commands import SaveHardwareConfigCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase


class SaveHardwareConfigUseCase(BaseUseCase[SaveHardwareConfigCommand]):
    name = "SaveHardwareConfigUseCase"

    def __init__(self, hardware_settings_service) -> None:
        self._service = hardware_settings_service

    def execute(self, command: SaveHardwareConfigCommand) -> UseCaseResult:
        command.validate_context()
        self._service.save_one(command.device_type, dict(command.config))
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=command.device_type)
