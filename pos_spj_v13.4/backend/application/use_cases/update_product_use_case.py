"""Canonical use case for product updates."""

from __future__ import annotations

from backend.application.commands.product_commands import UpdateProductCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.services.product_catalog_service import ProductCatalogService
from backend.application.use_cases.base_use_case import BaseUseCase, UseCaseHandler


class UpdateProductUseCase(BaseUseCase[UpdateProductCommand]):
    name = "UpdateProductUseCase"

    def __init__(
        self,
        app_service: ProductCatalogService | None = None,
        handler: UseCaseHandler[UpdateProductCommand] | None = None,
    ) -> None:
        self._app_service = app_service
        self._handler = handler

    def execute(self, command: UpdateProductCommand) -> UseCaseResult:
        command.validate_context()
        if self._app_service is not None:
            return self._app_service.update(command)
        if self._handler is not None:
            return self._handler(command)
        return UseCaseResult.not_implemented(command.operation_id, use_case_name=self.name)
