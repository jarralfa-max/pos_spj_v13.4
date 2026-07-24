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
from backend.application.inventory.use_cases.quarantine_use_cases import (
    DisposeQuarantineUseCase,
    QuarantineStockUseCase,
    ReleaseQuarantineUseCase,
)
from backend.application.inventory.use_cases.register_traceability_link import (
    RegisterTraceabilityLinkUseCase,
)
from backend.application.inventory.use_cases.replenishment_use_cases import (
    GenerateReplenishmentSuggestionsUseCase,
    SetReplenishmentRuleUseCase,
)
from backend.application.inventory.use_cases.register_waste import RegisterWasteUseCase
from backend.application.inventory.use_cases.record_temperature_reading import (
    RecordTemperatureReadingUseCase,
)
from backend.application.inventory.use_cases.reservation_use_cases import (
    AllocateReservationUseCase,
    CreateReservationUseCase,
    ReleaseReservationUseCase,
)
from backend.application.inventory.use_cases.reverse_inventory_movement import (
    ReverseInventoryMovementUseCase,
)
from backend.application.inventory.use_cases.warehouse_use_cases import (
    CreateLocationUseCase,
    CreateWarehouseUseCase,
    CreateZoneUseCase,
    SetLocationStatusUseCase,
    SetWarehouseStatusUseCase,
)

__all__ = [
    "AllocateReservationUseCase",
    "ApproveAdjustmentUseCase",
    "ApproveCountUseCase",
    "ConfirmCountUseCase",
    "CreateAdjustmentFromCountUseCase",
    "CreateAdjustmentUseCase",
    "CreateCountUseCase",
    "CreateLocationUseCase",
    "CreateReservationUseCase",
    "CreateWarehouseUseCase",
    "CreateZoneUseCase",
    "DisposeQuarantineUseCase",
    "GenerateReplenishmentSuggestionsUseCase",
    "PostAdjustmentUseCase",
    "PostInventoryMovementUseCase",
    "QuarantineStockUseCase",
    "RecordCountUseCase",
    "RegisterTraceabilityLinkUseCase",
    "RegisterWasteUseCase",
    "SetLocationStatusUseCase",
    "SetReplenishmentRuleUseCase",
    "SetWarehouseStatusUseCase",
    "ReleaseQuarantineUseCase",
    "ReverseAdjustmentUseCase",
    "RecordTemperatureReadingUseCase",
    "RegisterInventoryLotUseCase",
    "ReleaseReservationUseCase",
    "ReverseInventoryMovementUseCase",
    "SetLotQualityStatusUseCase",
]
