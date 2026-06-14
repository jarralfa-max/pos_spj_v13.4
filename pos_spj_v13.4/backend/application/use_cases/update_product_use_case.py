"""Canonical use case for updating products."""

from __future__ import annotations

from backend.application.commands.product_commands import UpdateProductCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase, UseCaseHandler


class UpdateProductUseCase(BaseUseCase[UpdateProductCommand]):
    name = "UpdateProductUseCase"

    def __init__(self, app_service=None, handler: UseCaseHandler[UpdateProductCommand] | None = None) -> None:
        self._app_service = app_service
        self._handler = handler

    def execute(self, command: UpdateProductCommand) -> UseCaseResult:
        command.validate_context()
        if self._handler is not None:
            return self._handler(command)
        if self._app_service is None:
            return UseCaseResult.not_implemented(command.operation_id, use_case_name=self.name)
        data = self._app_service.update_product(command)
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=str(data.get("product_id")) if isinstance(data, dict) and data.get("product_id") is not None else None, data=data if isinstance(data, dict) else {"result": data})
