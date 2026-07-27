"""Execute monthly closing use case — single canonical route."""

from __future__ import annotations

from backend.application.commands.settings_commands import ExecuteMonthlyClosingCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase


class ExecuteMonthlyClosingUseCase(BaseUseCase[ExecuteMonthlyClosingCommand]):
    name = "ExecuteMonthlyClosingUseCase"

    def __init__(self, closing_period_service) -> None:
        self._service = closing_period_service

    def execute(self, command: ExecuteMonthlyClosingCommand) -> UseCaseResult:
        command.validate_context()
        if self._service.period_exists(command.period):
            return UseCaseResult(
                success=False,
                operation_id=command.operation_id,
                message=f"period {command.period} already closed",
            )
        payload = command.payload or {}
        totals = {
            "sales": float(payload.get("sales", 0) or 0),
            "purchases": float(payload.get("purchases", 0) or 0),
            "waste": float(payload.get("waste", 0) or 0),
        }
        self._service.close_period(
            period=command.period,
            closed_by=command.user_name or "",
            totals=totals,
            branch_id=command.branch_id,
        )
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=command.period)
