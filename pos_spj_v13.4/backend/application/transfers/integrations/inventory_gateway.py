"""Single canonical adapter from Transfers to Inventory application use cases."""
from dataclasses import dataclass
from typing import Protocol

from backend.domain.transfers.entities.stock_transfer import StockTransfer, TransferReceipt
from backend.domain.transfers.entities.transfer_return import TransferReturn
from backend.domain.transfers.policies.lot_allocation_policy import TransferLotAllocation


@dataclass(frozen=True, slots=True)
class InventoryTransferRequest:
    transfer: StockTransfer
    operation_id: str
    actor_id: str
    receipt: TransferReceipt | None = None
    allocations: tuple[TransferLotAllocation, ...] = ()


@dataclass(frozen=True, slots=True)
class InventoryReturnRequest:
    transfer_return: TransferReturn
    operation_id: str
    actor_id: str


class ReserveInventoryUseCase(Protocol):
    def execute(self, request: InventoryTransferRequest) -> None: ...


class AllocateInventoryUseCase(Protocol):
    def execute(self, request: InventoryTransferRequest) -> None: ...


class PostTransferDispatchUseCase(Protocol):
    def execute(self, request: InventoryTransferRequest) -> None: ...


class PostTransferReceiptUseCase(Protocol):
    def execute(self, request: InventoryTransferRequest) -> None: ...


class PostTransferReturnUseCase(Protocol):
    def dispatch(self, request: InventoryReturnRequest) -> None: ...
    def receive(self, request: InventoryReturnRequest) -> None: ...


class CanonicalInventoryTransferGateway:
    """Has no fallback: every mutation delegates to one injected Inventory use case."""
    def __init__(self, reserve: ReserveInventoryUseCase, allocate: AllocateInventoryUseCase,
                 dispatch: PostTransferDispatchUseCase, receipt: PostTransferReceiptUseCase,
                 transfer_return: PostTransferReturnUseCase) -> None:
        self._reserve = reserve
        self._allocate = allocate
        self._dispatch = dispatch
        self._receipt = receipt
        self._return = transfer_return

    def reserve(self, *, transfer: StockTransfer, operation_id: str, actor_id: str,
                allocations: tuple[TransferLotAllocation, ...] = ()) -> None:
        request = InventoryTransferRequest(transfer, operation_id, actor_id,
                                           allocations=allocations)
        self._reserve.execute(request)
        if allocations:
            self._allocate.execute(request)

    def dispatch(self, *, transfer: StockTransfer, operation_id: str, actor_id: str) -> None:
        self._dispatch.execute(InventoryTransferRequest(transfer, operation_id, actor_id))

    def receive(self, *, transfer: StockTransfer, receipt: TransferReceipt,
                operation_id: str, actor_id: str) -> None:
        self._receipt.execute(InventoryTransferRequest(
            transfer, operation_id, actor_id, receipt=receipt))

    def dispatch_return(self, *, transfer_return: TransferReturn,
                        operation_id: str, actor_id: str) -> None:
        self._return.dispatch(InventoryReturnRequest(transfer_return, operation_id, actor_id))

    def receive_return(self, *, transfer_return: TransferReturn,
                       operation_id: str, actor_id: str) -> None:
        self._return.receive(InventoryReturnRequest(transfer_return, operation_id, actor_id))
