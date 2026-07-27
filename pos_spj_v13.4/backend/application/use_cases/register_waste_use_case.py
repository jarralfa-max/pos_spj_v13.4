"""Canonical use case for waste registration."""

from __future__ import annotations

from backend.application.commands.waste_commands import RegisterWasteCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.services.waste_application_service import WasteApplicationService
from backend.application.use_cases.base_use_case import BaseUseCase, UseCaseHandler


class RegisterWasteUseCase(BaseUseCase[RegisterWasteCommand]):
    name = "RegisterWasteUseCase"

    def __init__(
        self,
        app_service: WasteApplicationService | None = None,
        handler: UseCaseHandler[RegisterWasteCommand] | None = None,
    ) -> None:
        self._app_service = app_service
        self._handler = handler

    def execute(self, command: RegisterWasteCommand) -> UseCaseResult:
        command.validate_context()
        if self._app_service is not None:
            return self._app_service.register(command)
        if self._handler is not None:
            return self._handler(command)
        return UseCaseResult.not_implemented(command.operation_id, use_case_name=self.name)
