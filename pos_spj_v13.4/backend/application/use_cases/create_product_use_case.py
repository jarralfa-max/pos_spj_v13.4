"""Canonical use case for creating products."""

from __future__ import annotations

from backend.application.commands.product_commands import CreateProductCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase, UseCaseHandler


class CreateProductUseCase(BaseUseCase[CreateProductCommand]):
    name = "CreateProductUseCase"

    def __init__(self, app_service=None, handler: UseCaseHandler[CreateProductCommand] | None = None) -> None:
        self._app_service = app_service
        self._handler = handler

    def execute(self, command: CreateProductCommand) -> UseCaseResult:
        command.validate_context()
        if self._handler is not None:
            return self._handler(command)
        if self._app_service is None:
            return UseCaseResult.not_implemented(command.operation_id, use_case_name=self.name)
        data = self._app_service.create_product(command)
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=str(data.get("product_id")) if isinstance(data, dict) and data.get("product_id") is not None else None, data=data if isinstance(data, dict) else {"result": data})
