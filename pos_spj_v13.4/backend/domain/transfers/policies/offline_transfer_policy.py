"""Closed offline-operation policy; critical authority always stays online."""
from dataclasses import dataclass
from enum import Enum

from backend.domain.transfers.exceptions import OfflineOperationNotAllowedError


class OfflineTransferOperation(str, Enum):
    PICK = "PICK"
    WEIGH = "WEIGH"
    SCAN = "SCAN"
    DISPATCH = "DISPATCH"
    RECEIVE = "RECEIVE"
    EVIDENCE = "EVIDENCE"
    TEMPERATURE = "TEMPERATURE"


@dataclass(frozen=True, slots=True)
class OfflineTransferPolicy:
    enabled_operations: frozenset[OfflineTransferOperation]

    def require_allowed(self, operation: OfflineTransferOperation) -> None:
        if operation not in self.enabled_operations:
            raise OfflineOperationNotAllowedError(
                f"Offline transfer operation is not enabled: {operation.value}")
