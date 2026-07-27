"""Set happy hour rule active use case — single canonical route."""

from __future__ import annotations

from backend.application.commands.settings_commands import SetHappyHourRuleActiveCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase


class SetHappyHourRuleActiveUseCase(BaseUseCase[SetHappyHourRuleActiveCommand]):
    name = "SetHappyHourRuleActiveUseCase"

    def __init__(self, happy_hour_settings_service) -> None:
        self._service = happy_hour_settings_service

    def execute(self, command: SetHappyHourRuleActiveCommand) -> UseCaseResult:
        command.validate_context()
        self._service.set_rule_active(command.rule_id, command.active)
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=command.rule_id)
