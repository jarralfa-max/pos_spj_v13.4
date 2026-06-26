"""Use case for recording a canonical inventory movement."""

from __future__ import annotations

from backend.application.commands.inventory_commands import RegisterInventoryMovementCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.services.inventory_application_service import InventoryApplicationService
from backend.application.use_cases.base_use_case import BaseUseCase


class RegisterInventoryMovementUseCase(BaseUseCase[RegisterInventoryMovementCommand]):
    name = "RegisterInventoryMovementUseCase"

    def __init__(self, app_service: InventoryApplicationService) -> None:
        self._app_service = app_service

    def execute(self, command: RegisterInventoryMovementCommand) -> UseCaseResult:
        command.validate_context()
        movement_type = command.movement_type.upper()
        if movement_type in {"INCREASE", "ENTRY", "PURCHASE", "TRANSFER_IN"}:
            result = self._app_service.increase_stock(
                command.product_id,
                command.branch_id,
                command.quantity,
                command.unit,
                command.reason,
                command.operation_id,
                command.source_module,
                command.reference_type,
                command.reference_id,
                command.user_name or "",
            )
        else:
            result = self._app_service.decrease_stock(
                command.product_id,
                command.branch_id,
                command.quantity,
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
