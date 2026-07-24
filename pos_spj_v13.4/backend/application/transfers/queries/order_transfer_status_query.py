"""Sales/POS-facing status contract; implementations remain read-only."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True, slots=True)
class OrderTransferStatusDTO:
    source_reference_id: str
    transfer_id: str
    transfer_status: str
    expected_arrival_at: str | None
    available_to_promise: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.available_to_promise, Decimal):
            raise TypeError("available_to_promise must be Decimal")


class OrderTransferStatusQueryService(Protocol):
    def get_for_source_reference(self, source_reference_id: str) -> OrderTransferStatusDTO | None: ...
