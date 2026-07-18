"""Inventory application use cases (INV-6+)."""

from backend.application.inventory.use_cases.lot_use_cases import (
    RegisterInventoryLotUseCase,
    SetLotQualityStatusUseCase,
)
from backend.application.inventory.use_cases.adjustment_use_cases import (
    ApproveAdjustmentUseCase,
    CreateAdjustmentFromCountUseCase,
    CreateAdjustmentUseCase,
    PostAdjustmentUseCase,
    ReverseAdjustmentUseCase,
)
from backend.application.inventory.use_cases.count_use_cases import (
    ApproveCountUseCase,
    ConfirmCountUseCase,
    CreateCountUseCase,
    RecordCountUseCase,
)
from backend.application.inventory.use_cases.post_inventory_movement import (
    PostInventoryMovementUseCase,
)
from backend.application.inventory.use_cases.record_temperature_reading import (
    RecordTemperatureReadingUseCase,
)
from backend.application.inventory.use_cases.reservation_use_cases import (
    AllocateReservationUseCase,
    CreateReservationUseCase,
    ReleaseReservationUseCase,
)
from backend.application.inventory.use_cases.transfer_use_cases import (
    ApproveTransferUseCase,
    CreateTransferUseCase,
    DispatchTransferUseCase,
    ReceiveTransferUseCase,
)
from backend.application.inventory.use_cases.reverse_inventory_movement import (
    ReverseInventoryMovementUseCase,
)

__all__ = [
    "AllocateReservationUseCase",
    "ApproveAdjustmentUseCase",
    "ApproveCountUseCase",
    "ApproveTransferUseCase",
    "ConfirmCountUseCase",
    "CreateAdjustmentFromCountUseCase",
    "CreateAdjustmentUseCase",
    "CreateCountUseCase",
    "CreateReservationUseCase",
    "CreateTransferUseCase",
    "DispatchTransferUseCase",
    "PostAdjustmentUseCase",
    "PostInventoryMovementUseCase",
    "ReceiveTransferUseCase",
    "RecordCountUseCase",
    "ReverseAdjustmentUseCase",
    "RecordTemperatureReadingUseCase",
    "RegisterInventoryLotUseCase",
    "ReleaseReservationUseCase",
    "ReverseInventoryMovementUseCase",
    "SetLotQualityStatusUseCase",
]
