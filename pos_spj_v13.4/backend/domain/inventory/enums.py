"""Canonical enums for the inventory bounded context.

INV-1 added the security enums (LimitDecision/LimitBasis/InventoryDuty).
INV-2 adds the operational vocabulary: warehouse/zone/location types and states,
inventory statuses, movement types + their balance direction.
"""

from __future__ import annotations

from enum import Enum


# ── INV-1 security enums ────────────────────────────────────────────────────
class LimitDecision(str, Enum):
    WITHIN = "WITHIN"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"
    EXCEEDS = "EXCEEDS"


class LimitBasis(str, Enum):
    QUANTITY = "QUANTITY"
    WEIGHT = "WEIGHT"
    VALUE = "VALUE"
    VARIANCE_PCT = "VARIANCE_PCT"


class InventoryDuty(str, Enum):
    WAREHOUSE_CLERK = "WAREHOUSE_CLERK"
    WAREHOUSE_SUPERVISOR = "WAREHOUSE_SUPERVISOR"
    RECEIVER = "RECEIVER"
    DISPATCHER = "DISPATCHER"
    PHYSICAL_COUNTER = "PHYSICAL_COUNTER"
    ADJUSTMENT_APPROVER = "ADJUSTMENT_APPROVER"
    QUALITY = "QUALITY"
    AUDITOR = "AUDITOR"
    CONFIG_ADMIN = "CONFIG_ADMIN"


# ── INV-2 warehouse / location ──────────────────────────────────────────────
class WarehouseType(str, Enum):
    STORE = "STORE"
    CENTRAL = "CENTRAL"
    DISTRIBUTION_CENTER = "DISTRIBUTION_CENTER"
    RAW_MATERIAL = "RAW_MATERIAL"
    FINISHED_GOODS = "FINISHED_GOODS"
    COLD_STORAGE = "COLD_STORAGE"
    FROZEN_STORAGE = "FROZEN_STORAGE"
    QUARANTINE = "QUARANTINE"
    PRODUCTION = "PRODUCTION"
    RETURNS = "RETURNS"
    DAMAGED = "DAMAGED"
    TRANSIT = "TRANSIT"
    VIRTUAL = "VIRTUAL"


class WarehouseStatus(str, Enum):
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    INACTIVE = "INACTIVE"


class WarehouseZoneType(str, Enum):
    RECEIVING = "RECEIVING"
    AVAILABLE = "AVAILABLE"
    PICKING = "PICKING"
    RESERVE = "RESERVE"
    COLD = "COLD"
    FROZEN = "FROZEN"
    QUARANTINE = "QUARANTINE"
    DAMAGED = "DAMAGED"
    RETURNS = "RETURNS"
    DISPATCH = "DISPATCH"


class LocationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    INACTIVE = "INACTIVE"


# ── INV-2 inventory status (§13) ────────────────────────────────────────────
class InventoryStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    ALLOCATED = "ALLOCATED"
    IN_TRANSIT = "IN_TRANSIT"
    PENDING_INSPECTION = "PENDING_INSPECTION"
    QUARANTINED = "QUARANTINED"
    QUALITY_BLOCKED = "QUALITY_BLOCKED"
    DAMAGED = "DAMAGED"
    EXPIRED = "EXPIRED"
    RETURNED = "RETURNED"
    PRODUCTION_HOLD = "PRODUCTION_HOLD"
    RECALL_HOLD = "RECALL_HOLD"
    DISPOSED = "DISPOSED"


#: Statuses whose stock is physically present in the warehouse (on-hand).
ON_HAND_STATUSES = frozenset(
    s for s in InventoryStatus if s is not InventoryStatus.DISPOSED
)

#: Statuses that count toward available-to-promise (sellable/consumable).
SELLABLE_STATUSES = frozenset({InventoryStatus.AVAILABLE})


def is_sellable(status: "InventoryStatus") -> bool:
    return status in SELLABLE_STATUSES


# ── INV-2 movement types (§15) + balance direction ──────────────────────────
class MovementType(str, Enum):
    PURCHASE_RECEIPT = "PURCHASE_RECEIPT"
    DIRECT_PURCHASE_RECEIPT = "DIRECT_PURCHASE_RECEIPT"
    SALE_ISSUE = "SALE_ISSUE"
    SALE_RETURN = "SALE_RETURN"
    TRANSFER_DISPATCH = "TRANSFER_DISPATCH"
    TRANSFER_RECEIPT = "TRANSFER_RECEIPT"
    PRODUCTION_CONSUMPTION = "PRODUCTION_CONSUMPTION"
    PRODUCTION_OUTPUT = "PRODUCTION_OUTPUT"
    SLAUGHTER_INPUT_FUTURE = "SLAUGHTER_INPUT_FUTURE"
    SLAUGHTER_OUTPUT_FUTURE = "SLAUGHTER_OUTPUT_FUTURE"
    KIT_ASSEMBLY = "KIT_ASSEMBLY"
    KIT_DISASSEMBLY = "KIT_DISASSEMBLY"
    QUALITY_BLOCK = "QUALITY_BLOCK"
    QUALITY_RELEASE = "QUALITY_RELEASE"
    QUARANTINE_ENTRY = "QUARANTINE_ENTRY"
    QUARANTINE_RELEASE = "QUARANTINE_RELEASE"
    ADJUSTMENT_IN = "ADJUSTMENT_IN"
    ADJUSTMENT_OUT = "ADJUSTMENT_OUT"
    COUNT_VARIANCE = "COUNT_VARIANCE"
    WASTE = "WASTE"
    SHRINKAGE = "SHRINKAGE"
    EXPIRY_DISPOSAL = "EXPIRY_DISPOSAL"
    SUPPLIER_RETURN = "SUPPLIER_RETURN"
    CUSTOMER_RETURN = "CUSTOMER_RETURN"
    REVERSAL = "REVERSAL"


class MovementDirection(str, Enum):
    INCREASE = "INCREASE"          # net on-hand goes up (destination line)
    DECREASE = "DECREASE"          # net on-hand goes down (source line)
    STATUS_TRANSFER = "STATUS_TRANSFER"  # same on-hand, changes status bucket
    VARIANCE = "VARIANCE"          # signed (count adjustment, may be + or -)
    MIXED = "MIXED"                # per-line (kit assembly/disassembly, reversal)


#: Balance effect of each movement type at the header level. Per-line effects
#: for MIXED types are resolved by the balance service (INV-6).
MOVEMENT_DIRECTION: dict[MovementType, MovementDirection] = {
    MovementType.PURCHASE_RECEIPT: MovementDirection.INCREASE,
    MovementType.DIRECT_PURCHASE_RECEIPT: MovementDirection.INCREASE,
    MovementType.SALE_RETURN: MovementDirection.INCREASE,
    MovementType.CUSTOMER_RETURN: MovementDirection.INCREASE,
    MovementType.TRANSFER_RECEIPT: MovementDirection.INCREASE,
    MovementType.PRODUCTION_OUTPUT: MovementDirection.INCREASE,
    MovementType.SLAUGHTER_OUTPUT_FUTURE: MovementDirection.INCREASE,
    MovementType.ADJUSTMENT_IN: MovementDirection.INCREASE,
    MovementType.SALE_ISSUE: MovementDirection.DECREASE,
    MovementType.TRANSFER_DISPATCH: MovementDirection.DECREASE,
    MovementType.PRODUCTION_CONSUMPTION: MovementDirection.DECREASE,
    MovementType.SLAUGHTER_INPUT_FUTURE: MovementDirection.DECREASE,
    MovementType.ADJUSTMENT_OUT: MovementDirection.DECREASE,
    MovementType.WASTE: MovementDirection.DECREASE,
    MovementType.SHRINKAGE: MovementDirection.DECREASE,
    MovementType.EXPIRY_DISPOSAL: MovementDirection.DECREASE,
    MovementType.SUPPLIER_RETURN: MovementDirection.DECREASE,
    MovementType.QUALITY_BLOCK: MovementDirection.STATUS_TRANSFER,
    MovementType.QUALITY_RELEASE: MovementDirection.STATUS_TRANSFER,
    MovementType.QUARANTINE_ENTRY: MovementDirection.STATUS_TRANSFER,
    MovementType.QUARANTINE_RELEASE: MovementDirection.STATUS_TRANSFER,
    MovementType.COUNT_VARIANCE: MovementDirection.VARIANCE,
    MovementType.KIT_ASSEMBLY: MovementDirection.MIXED,
    MovementType.KIT_DISASSEMBLY: MovementDirection.MIXED,
    MovementType.REVERSAL: MovementDirection.MIXED,
}


def movement_direction(movement_type: "MovementType") -> "MovementDirection":
    return MOVEMENT_DIRECTION[movement_type]


class MovementStatus(str, Enum):
    DRAFT = "DRAFT"
    POSTED = "POSTED"
    REVERSED = "REVERSED"


# ── INV-7 lots / expiration ─────────────────────────────────────────────────
class LotOrigin(str, Enum):
    PURCHASE = "PURCHASE"
    PRODUCTION = "PRODUCTION"
    SLAUGHTER_FUTURE = "SLAUGHTER_FUTURE"
    CUSTOMER_RETURN = "CUSTOMER_RETURN"
    TRANSFER = "TRANSFER"
    MANUAL_AUTHORIZED = "MANUAL_AUTHORIZED"


class LotQualityStatus(str, Enum):
    PENDING_INSPECTION = "PENDING_INSPECTION"
    RELEASED = "RELEASED"
    BLOCKED = "BLOCKED"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"


class AllocationStrategy(str, Enum):
    FIFO = "FIFO"
    FEFO = "FEFO"          # first-expired, first-out (default for perishables)
    LIFO = "LIFO"
    MANUAL_AUTHORIZED = "MANUAL_AUTHORIZED"


class ExpiryRisk(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    EXPIRED = "EXPIRED"


# ── INV-8 catch weight ──────────────────────────────────────────────────────
class WeightCaptureSource(str, Enum):
    SCALE = "SCALE"
    MANUAL_AUTHORIZED = "MANUAL_AUTHORIZED"
    IMPORT = "IMPORT"
    PRODUCTION = "PRODUCTION"
    RECEIVING = "RECEIVING"


# ── INV-9 cold chain ────────────────────────────────────────────────────────
class ColdChainStatus(str, Enum):
    COMPLIANT = "COMPLIANT"
    WARNING = "WARNING"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    PENDING_REVIEW = "PENDING_REVIEW"
    BLOCKED = "BLOCKED"


class TemperaturePoint(str, Enum):
    RECEIPT = "RECEIPT"
    STORAGE = "STORAGE"
    DISPATCH = "DISPATCH"
    TRANSIT = "TRANSIT"


class ExcursionAction(str, Enum):
    NONE = "NONE"
    WARN = "WARN"
    BLOCK_LOT = "BLOCK_LOT"
    QUARANTINE = "QUARANTINE"


# ── INV-10 reservations / allocations ───────────────────────────────────────
class ReservationSource(str, Enum):
    SALE = "SALE"
    CUSTOMER_ORDER = "CUSTOMER_ORDER"
    DELIVERY_ORDER = "DELIVERY_ORDER"
    PRODUCTION_ORDER = "PRODUCTION_ORDER"
    TRANSFER = "TRANSFER"
    QUALITY_SAMPLE = "QUALITY_SAMPLE"
    INTERNAL_REQUEST = "INTERNAL_REQUEST"


class ReservationStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    PARTIALLY_ALLOCATED = "PARTIALLY_ALLOCATED"
    ALLOCATED = "ALLOCATED"
    PARTIALLY_FULFILLED = "PARTIALLY_FULFILLED"
    FULFILLED = "FULFILLED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class AllocationStatus(str, Enum):
    ALLOCATED = "ALLOCATED"
    FULFILLED = "FULFILLED"
    RELEASED = "RELEASED"


#: Reservation statuses that still hold availability (reduce available-to-promise).
ACTIVE_RESERVATION_STATUSES = frozenset({
    ReservationStatus.PENDING, ReservationStatus.CONFIRMED,
    ReservationStatus.PARTIALLY_ALLOCATED, ReservationStatus.ALLOCATED,
    ReservationStatus.PARTIALLY_FULFILLED,
})
