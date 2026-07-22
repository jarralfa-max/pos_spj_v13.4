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


# ── INV-12 transfers ────────────────────────────────────────────────────────
class TransferStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    PICKING = "PICKING"
    READY_TO_DISPATCH = "READY_TO_DISPATCH"
    IN_TRANSIT = "IN_TRANSIT"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    RECEIVED = "RECEIVED"
    WITH_DIFFERENCES = "WITH_DIFFERENCES"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class TransferDifferenceType(str, Enum):
    SHORT = "SHORT"
    OVER = "OVER"
    DAMAGED = "DAMAGED"
    WRONG_PRODUCT = "WRONG_PRODUCT"
    WEIGHT_VARIANCE = "WEIGHT_VARIANCE"
    LOT_VARIANCE = "LOT_VARIANCE"
    TEMPERATURE_VARIANCE = "TEMPERATURE_VARIANCE"
    QUALITY_FAILURE = "QUALITY_FAILURE"


# ── INV-13 counts ───────────────────────────────────────────────────────────
class CountType(str, Enum):
    CYCLE_COUNT = "CYCLE_COUNT"
    FULL_COUNT = "FULL_COUNT"
    LOCATION_COUNT = "LOCATION_COUNT"
    PRODUCT_COUNT = "PRODUCT_COUNT"
    LOT_COUNT = "LOT_COUNT"
    BLIND_COUNT = "BLIND_COUNT"
    SPOT_CHECK = "SPOT_CHECK"


class CountStatus(str, Enum):
    DRAFT = "DRAFT"
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COUNTED = "COUNTED"
    PENDING_RECOUNT = "PENDING_RECOUNT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


# ── INV-14 adjustments ──────────────────────────────────────────────────────
class AdjustmentReason(str, Enum):
    COUNT_VARIANCE = "COUNT_VARIANCE"
    DAMAGE = "DAMAGE"
    EXPIRY = "EXPIRY"
    SHRINKAGE = "SHRINKAGE"
    WASTE = "WASTE"
    THEFT_SUSPECTED = "THEFT_SUSPECTED"
    QUALITY_REJECTION = "QUALITY_REJECTION"
    SYSTEM_CORRECTION = "SYSTEM_CORRECTION"
    WEIGHT_VARIANCE = "WEIGHT_VARIANCE"
    MANUAL_AUTHORIZED = "MANUAL_AUTHORIZED"


class AdjustmentStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    POSTED = "POSTED"
    REVERSED = "REVERSED"
    CANCELLED = "CANCELLED"


# ── INV-15 quality / quarantine ─────────────────────────────────────────────
class QuarantineReason(str, Enum):
    PENDING_INSPECTION = "PENDING_INSPECTION"
    TEMPERATURE_EXCURSION = "TEMPERATURE_EXCURSION"
    QUALITY_FAILURE = "QUALITY_FAILURE"
    DOCUMENTATION_MISSING = "DOCUMENTATION_MISSING"
    RECALL = "RECALL"
    CUSTOMER_RETURN = "CUSTOMER_RETURN"
    SUPPLIER_DISPUTE = "SUPPLIER_DISPUTE"
    MICROBIOLOGICAL_TEST_FUTURE = "MICROBIOLOGICAL_TEST_FUTURE"


class QuarantineStatus(str, Enum):
    OPEN = "OPEN"
    UNDER_REVIEW = "UNDER_REVIEW"
    RELEASED = "RELEASED"
    PARTIALLY_RELEASED = "PARTIALLY_RELEASED"
    REJECTED = "REJECTED"
    DISPOSED = "DISPOSED"


# ── INV-16 waste / disposal (§30) ───────────────────────────────────────────
class WasteType(str, Enum):
    THEORETICAL_WASTE = "THEORETICAL_WASTE"   # standard/expected — no stock move
    ACTUAL_WASTE = "ACTUAL_WASTE"
    SHRINKAGE = "SHRINKAGE"
    PROCESS_LOSS = "PROCESS_LOSS"
    EXPIRY = "EXPIRY"
    DAMAGE = "DAMAGE"
    QUALITY_REJECTION = "QUALITY_REJECTION"
    CONDEMNATION = "CONDEMNATION"
    DISPOSAL = "DISPOSAL"


#: Physical-exit movement type per waste classification (THEORETICAL_WASTE moves
#: no stock — it is an informational/standard loss valued by production).
WASTE_MOVEMENT_TYPE: dict[WasteType, MovementType] = {
    WasteType.ACTUAL_WASTE: MovementType.WASTE,
    WasteType.PROCESS_LOSS: MovementType.WASTE,
    WasteType.DAMAGE: MovementType.WASTE,
    WasteType.QUALITY_REJECTION: MovementType.WASTE,
    WasteType.CONDEMNATION: MovementType.WASTE,
    WasteType.SHRINKAGE: MovementType.SHRINKAGE,
    WasteType.EXPIRY: MovementType.EXPIRY_DISPOSAL,
    WasteType.DISPOSAL: MovementType.EXPIRY_DISPOSAL,
}

#: Loss classifications that require the disposal-authorization permission.
DISPOSAL_WASTE_TYPES = frozenset({
    WasteType.EXPIRY, WasteType.DISPOSAL, WasteType.CONDEMNATION,
})


# ── INV-17 traceability (§32) ───────────────────────────────────────────────
class TraceabilityDirection(str, Enum):
    UPSTREAM = "UPSTREAM"      # where the lot came from (supplier/production/slaughter)
    DOWNSTREAM = "DOWNSTREAM"  # where the lot went (sale/transfer/consumption)


class TraceabilityLinkType(str, Enum):
    """Explicit genealogy edges (parent lot → child lot) for transformations that
    the ledger alone cannot infer (production/slaughter break a lot's identity)."""
    PRODUCTION = "PRODUCTION"          # input lots consumed → output lot
    SLAUGHTER = "SLAUGHTER"            # carcass lot → cut/piece lots (future §33)
    REPACK = "REPACK"                  # relabel/repackage into a new lot
    TRANSFORMATION = "TRANSFORMATION"  # generic transformation
    SPLIT = "SPLIT"                    # one lot → many child lots
    MERGE = "MERGE"                    # many lots → one child lot
