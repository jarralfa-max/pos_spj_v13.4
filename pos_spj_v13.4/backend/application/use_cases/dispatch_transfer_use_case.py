"""Use case: Dispatch a transfer (Phase 1 — deducts origin stock)."""

from __future__ import annotations

import logging

from backend.application.commands.transfer_commands import DispatchTransferCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase

logger = logging.getLogger("spj.use_cases.dispatch_transfer")


class DispatchTransferUseCase(BaseUseCase[DispatchTransferCommand]):
    """
    Validate and execute a transfer dispatch.

    Delegates persistence and stock deduction to TransferRepository so no SQL
    lives here. The repository raises TransferStockError / TransferError on
    business rule violations; these propagate to the caller.
    """

    name = "DispatchTransferUseCase"

    def __init__(self, repository) -> None:
        self._repo = repository

    def execute(self, command: DispatchTransferCommand) -> UseCaseResult:
        command.validate_context()

        if not command.items:
            return UseCaseResult(
                success=False,
                operation_id=command.operation_id,
                message="El despacho debe contener al menos un producto.",
            )
        if command.origin_branch_id == command.dest_branch_id:
            return UseCaseResult(
                success=False,
                operation_id=command.operation_id,
                message="Origen y destino no pueden ser la misma sucursal.",
            )
        if not command.dispatched_by:
            return UseCaseResult(
                success=False,
                operation_id=command.operation_id,
                message="Debe indicarse quién entrega la transferencia.",
            )

        repo_items = [
            {
                "product_id":    item.product_id,
                "quantity_sent": item.quantity_sent,
                "unit":          item.unit,
                "notes":         item.notes,
            }
            for item in command.items
        ]

        transfer_id = self._repo.dispatch(
            origin_branch_id=command.origin_branch_id,
            dest_branch_id=command.dest_branch_id,
            items=repo_items,
            dispatched_by=command.dispatched_by,
            origin_type=command.origin_type,
            destination_type=command.destination_type,
            observations=command.observations,
        )

        logger.info(
            "DispatchTransferUseCase ok transfer_id=%s operation_id=%s",
            transfer_id,
            command.operation_id,
        )
        return UseCaseResult(
            success=True,
            operation_id=command.operation_id,
            entity_id=str(transfer_id),
            message="Transferencia despachada correctamente.",
        )
