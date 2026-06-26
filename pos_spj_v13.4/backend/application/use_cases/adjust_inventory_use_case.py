"""Use case for canonical inventory adjustments."""

from __future__ import annotations

from backend.application.commands.inventory_commands import AdjustInventoryCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.services.inventory_application_service import InventoryApplicationService
from backend.application.use_cases.base_use_case import BaseUseCase


class AdjustInventoryUseCase(BaseUseCase[AdjustInventoryCommand]):
    name = "AdjustInventoryUseCase"

    def __init__(self, app_service: InventoryApplicationService) -> None:
        self._app_service = app_service

    def execute(self, command: AdjustInventoryCommand) -> UseCaseResult:
        command.validate_context()
        result = self._app_service.adjust_stock(
            command.product_id,
            command.branch_id,
            command.new_quantity,
            command.unit,
            command.reason,
            command.operation_id,
            command.source_module,
            command.reference_type,
            command.reference_id,
            command.user_name or "",
        )
        return UseCaseResult(
            result.success,
            result.operation_id,
            entity_id=str(command.product_id),
            message=result.message or result.movement_type,
            data={"stock_before": result.stock_before, "stock_after": result.stock_after},
            events=result.events,
        )
