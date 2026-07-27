"""Canonical use case for sale creation."""

from __future__ import annotations

from backend.application.commands.sales_commands import CreateSaleCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.services.sales_application_service import SalesApplicationService
from backend.application.use_cases.base_use_case import BaseUseCase, UseCaseHandler


class CreateSaleUseCase(BaseUseCase[CreateSaleCommand]):
    name = "CreateSaleUseCase"

    def __init__(
        self,
        handler: UseCaseHandler[CreateSaleCommand] | None = None,
        app_service: SalesApplicationService | None = None,
    ) -> None:
        self._handler = handler
        self._app_service = app_service

    def execute(self, command: CreateSaleCommand) -> UseCaseResult:
        command.validate_context()
        if self._app_service is not None:
            return self._app_service.create(command)
        if self._handler is not None:
            return self._handler(command)
        return UseCaseResult.not_implemented(command.operation_id, use_case_name=self.name)
