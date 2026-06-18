"""Use case: Receive a dispatched transfer (Phase 2 — credits destination stock)."""

from __future__ import annotations

import logging

from backend.application.commands.transfer_commands import ReceiveTransferCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase

logger = logging.getLogger("spj.use_cases.receive_transfer")


class ReceiveTransferUseCase(BaseUseCase[ReceiveTransferCommand]):
    """
    Validate and execute a transfer reception.

    Delegates persistence and stock credit to TransferRepository.
    """

    name = "ReceiveTransferUseCase"

    def __init__(self, repository) -> None:
        self._repo = repository

    def execute(self, command: ReceiveTransferCommand) -> UseCaseResult:
        command.validate_context()

        if not command.transfer_id:
            return UseCaseResult(
                success=False,
                operation_id=command.operation_id,
                message="Se requiere el ID de la transferencia a recepcionar.",
            )
        if not command.received_by:
            return UseCaseResult(
                success=False,
                operation_id=command.operation_id,
                message="Debe indicarse quién recibe la transferencia.",
            )

        received_items = [
            {
                "product_id":        item.product_id,
                "quantity_received": item.quantity_received,
                "notes":             item.notes,
            }
            for item in command.received_items
        ]

        result = self._repo.receive(
            transfer_id=command.transfer_id,
            received_by=command.received_by,
            received_items=received_items,
            observations=command.observations,
        )

        logger.info(
            "ReceiveTransferUseCase ok transfer_id=%s operation_id=%s",
            command.transfer_id,
            command.operation_id,
        )
        return UseCaseResult(
            success=True,
            operation_id=command.operation_id,
            entity_id=command.transfer_id,
            message="Transferencia recepcionada correctamente.",
            data=result or {},
        )
