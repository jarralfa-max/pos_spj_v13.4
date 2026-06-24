"""Save happy hour rule use case — single canonical route."""

from __future__ import annotations

from backend.application.commands.settings_commands import SaveHappyHourRuleCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase


class SaveHappyHourRuleUseCase(BaseUseCase[SaveHappyHourRuleCommand]):
    name = "SaveHappyHourRuleUseCase"

    def __init__(self, happy_hour_settings_service) -> None:
        self._service = happy_hour_settings_service

    def execute(self, command: SaveHappyHourRuleCommand) -> UseCaseResult:
        command.validate_context()
        rule = {
            "id": command.rule_id or "",
            "nombre": command.name,
            "hora_inicio": command.start_time,
            "hora_fin": command.end_time,
            "dias_semana": ",".join(str(day) for day in command.days_of_week),
            "tipo_descuento": "porcentaje",
            "valor": float(command.discount_percent),
            "aplica_a": "todos",
            "aplica_valor": "",
            "activo": command.active,
            "sucursal_id": command.branch_id,
            "message": "",
        }
        rule_id = self._service.save_rule(rule)
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=rule_id)
