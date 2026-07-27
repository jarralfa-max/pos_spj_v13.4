"""Use case: Cancel a pending or dispatched transfer."""

from __future__ import annotations

import logging

from backend.application.commands.transfer_commands import CancelTransferCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase

logger = logging.getLogger("spj.use_cases.cancel_transfer")


class CancelTransferUseCase(BaseUseCase[CancelTransferCommand]):
    """Cancel a transfer and restore origin stock if it was already dispatched."""

    name = "CancelTransferUseCase"

    def __init__(self, repository) -> None:
        self._repo = repository

    def execute(self, command: CancelTransferCommand) -> UseCaseResult:
        command.validate_context()

        if not command.transfer_id:
            return UseCaseResult(
                success=False,
                operation_id=command.operation_id,
                message="Se requiere el ID de la transferencia a cancelar.",
            )

        self._repo.cancel(
            command.transfer_id,
            command.user_name or command.user_id or "Sistema",
            command.reason,
        )

        logger.info(
            "CancelTransferUseCase ok transfer_id=%s operation_id=%s",
            command.transfer_id,
            command.operation_id,
        )
        return UseCaseResult(
            success=True,
            operation_id=command.operation_id,
            entity_id=command.transfer_id,
            message="Transferencia cancelada. Stock restaurado en origen.",
        )
