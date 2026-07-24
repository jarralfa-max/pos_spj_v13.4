"""Read-only policy for legal workflow transitions and terminal states."""
from ..enums import TransferStatus


class TransferWorkflowPolicy:
    _TRANSITIONS = {
        TransferStatus.DRAFT: frozenset((TransferStatus.PENDING_APPROVAL, TransferStatus.CANCELLED)),
        TransferStatus.PENDING_APPROVAL: frozenset((TransferStatus.APPROVED, TransferStatus.REJECTED, TransferStatus.CANCELLED)),
        TransferStatus.APPROVED: frozenset((TransferStatus.RESERVATION_PENDING, TransferStatus.RESERVED, TransferStatus.CANCELLED)),
        TransferStatus.RESERVATION_PENDING: frozenset((TransferStatus.RESERVED, TransferStatus.CANCELLED)),
        TransferStatus.RESERVED: frozenset((TransferStatus.PICKING, TransferStatus.CANCELLED)),
        TransferStatus.PICKING: frozenset((TransferStatus.PARTIALLY_PICKED, TransferStatus.PICKED, TransferStatus.READY_TO_DISPATCH, TransferStatus.CANCELLED)),
        TransferStatus.PARTIALLY_PICKED: frozenset((TransferStatus.PICKING, TransferStatus.PICKED, TransferStatus.READY_TO_DISPATCH, TransferStatus.CANCELLED)),
        TransferStatus.PICKED: frozenset((TransferStatus.READY_TO_DISPATCH, TransferStatus.CANCELLED)),
        TransferStatus.READY_TO_DISPATCH: frozenset((TransferStatus.PARTIALLY_DISPATCHED, TransferStatus.IN_TRANSIT, TransferStatus.CANCELLED)),
        TransferStatus.PARTIALLY_DISPATCHED: frozenset((TransferStatus.IN_TRANSIT,)),
        TransferStatus.IN_TRANSIT: frozenset((TransferStatus.PARTIALLY_RECEIVED, TransferStatus.RECEIVED, TransferStatus.WITH_DIFFERENCES, TransferStatus.RETURN_IN_PROGRESS)),
        TransferStatus.PARTIALLY_RECEIVED: frozenset((TransferStatus.RECEIVED, TransferStatus.WITH_DIFFERENCES, TransferStatus.RETURN_IN_PROGRESS)),
        TransferStatus.RECEIVED: frozenset((TransferStatus.WITH_DIFFERENCES, TransferStatus.CLOSED, TransferStatus.REVERSED)),
        TransferStatus.WITH_DIFFERENCES: frozenset((TransferStatus.PENDING_RESOLUTION, TransferStatus.RETURN_IN_PROGRESS)),
        TransferStatus.PENDING_RESOLUTION: frozenset((TransferStatus.CLOSED, TransferStatus.RETURN_IN_PROGRESS)),
        TransferStatus.RETURN_IN_PROGRESS: frozenset((TransferStatus.CLOSED,)),
        TransferStatus.CLOSED: frozenset((TransferStatus.REVERSED,)),
        TransferStatus.REJECTED: frozenset(), TransferStatus.CANCELLED: frozenset(), TransferStatus.REVERSED: frozenset(),
    }

    def can_transition(self, current: TransferStatus, target: TransferStatus) -> bool:
        return target in self._TRANSITIONS[current]

    def is_terminal(self, status: TransferStatus) -> bool:
        return not self._TRANSITIONS[status]
