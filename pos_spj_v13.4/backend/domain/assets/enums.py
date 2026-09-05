"""Canonical enumerations for the Assets / EAM bounded context (ASSET-3, §16-17-18)."""

from __future__ import annotations

from enum import Enum


class AssetStatus(str, Enum):
    DRAFT = "DRAFT"
    AVAILABLE = "AVAILABLE"
    ASSIGNED = "ASSIGNED"
    IN_USE = "IN_USE"
    IN_MAINTENANCE = "IN_MAINTENANCE"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"
    LOANED = "LOANED"
    MISSING = "MISSING"
    DISPOSAL_PENDING = "DISPOSAL_PENDING"
    DISPOSED = "DISPOSED"
    SOLD = "SOLD"
    DONATED = "DONATED"
    STOLEN = "STOLEN"
    LOST = "LOST"


class AssetCondition(str, Enum):
    NEW = "NEW"
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"
    DAMAGED = "DAMAGED"
    UNUSABLE = "UNUSABLE"


class AssetCriticality(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AssetOwnershipType(str, Enum):
    OWNED = "OWNED"
    LEASED = "LEASED"
    RENTED = "RENTED"
    ON_LOAN_FROM_THIRD_PARTY = "ON_LOAN_FROM_THIRD_PARTY"


class AssetWarrantyStatus(str, Enum):
    NONE = "NONE"
    ACTIVE = "ACTIVE"
    EXPIRING = "EXPIRING"
    EXPIRED = "EXPIRED"
    VOID = "VOID"


class AssetLocationType(str, Enum):
    COMPANY = "COMPANY"
    BRANCH = "BRANCH"
    AREA = "AREA"
    ROOM = "ROOM"
    POSITION = "POSITION"


class AssetLocationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class AssetCategoryStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


# ── custodia (ASSET-4, §19) ──────────────────────────────────────────────────
class AssetAssignmentType(str, Enum):
    CUSTODY = "CUSTODY"
    OPERATION = "OPERATION"
    TEMPORARY_LOAN = "TEMPORARY_LOAN"
    SHARED = "SHARED"
    VEHICLE_ASSIGNMENT = "VEHICLE_ASSIGNMENT"


# ── transferencias (ASSET-5, §20) ────────────────────────────────────────────
class AssetTransferStatus(str, Enum):
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    PREPARED = "PREPARED"
    IN_TRANSIT = "IN_TRANSIT"
    RECEIVED = "RECEIVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


# ── mantenimiento (ASSET-6, §23, §25-27) ─────────────────────────────────────
class MaintenanceType(str, Enum):
    PREVENTIVE = "PREVENTIVE"
    CORRECTIVE = "CORRECTIVE"
    PREDICTIVE_FUTURE = "PREDICTIVE_FUTURE"
    INSPECTION = "INSPECTION"
    CALIBRATION = "CALIBRATION"
    SAFETY = "SAFETY"
    WARRANTY = "WARRANTY"
    EMERGENCY = "EMERGENCY"


class MaintenanceFrequencyType(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    SEMIANNUAL = "SEMIANNUAL"
    ANNUAL = "ANNUAL"
    METER_BASED = "METER_BASED"
    CUSTOM = "CUSTOM"


class MaintenancePlanStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    INACTIVE = "INACTIVE"


class MaintenanceProviderType(str, Enum):
    INTERNAL = "INTERNAL"
    EXTERNAL = "EXTERNAL"
    WARRANTY_PROVIDER = "WARRANTY_PROVIDER"


class MaintenanceWorkOrderStatus(str, Enum):
    DRAFT = "DRAFT"
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    SCHEDULED = "SCHEDULED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    PAUSED = "PAUSED"
    WAITING_PARTS = "WAITING_PARTS"
    WAITING_PROVIDER = "WAITING_PROVIDER"
    COMPLETED = "COMPLETED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


# ── inspecciones (ASSET-7, §37-38) ───────────────────────────────────────────
class InspectionType(str, Enum):
    SAFETY = "SAFETY"
    OPERATIONAL = "OPERATIONAL"
    QUALITY = "QUALITY"
    PREVENTIVE = "PREVENTIVE"
    CALIBRATION = "CALIBRATION"
    REGULATORY = "REGULATORY"


class InspectionResultStatus(str, Enum):
    PASS_ = "PASS"
    PASS_WITH_OBSERVATIONS = "PASS_WITH_OBSERVATIONS"
    FAIL = "FAIL"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"


class InspectionResponseType(str, Enum):
    BOOLEAN = "BOOLEAN"
    TEXT = "TEXT"
    NUMBER = "NUMBER"
    PHOTO = "PHOTO"
    SIGNATURE = "SIGNATURE"
    CHOICE = "CHOICE"


# ── medidores (ASSET-8, §39) ─────────────────────────────────────────────────
class AssetMeterType(str, Enum):
    HOURS = "HOURS"
    KILOMETERS = "KILOMETERS"
    CYCLES = "CYCLES"
    ENERGY = "ENERGY"
    CUSTOM = "CUSTOM"


# ── documentación / garantías / seguros (ASSET-9, §40-43) ───────────────────
class AssetDocumentType(str, Enum):
    INVOICE = "INVOICE"
    MANUAL = "MANUAL"
    WARRANTY = "WARRANTY"
    INSURANCE = "INSURANCE"
    PHOTO = "PHOTO"
    CERTIFICATE = "CERTIFICATE"
    SERVICE_REPORT = "SERVICE_REPORT"
    REGISTRATION = "REGISTRATION"
    OWNERSHIP = "OWNERSHIP"
    OTHER = "OTHER"


class AssetInsuranceStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRING = "EXPIRING"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


# ── costos / mejoras / capitalización propuesta (ASSET-10, §30, §36) ────────
class AssetCapitalizationProposalStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


# ── inventario físico (ASSET-11, §44-45) ─────────────────────────────────────
class AssetPhysicalInventoryStatus(str, Enum):
    DRAFT = "DRAFT"
    IN_PROGRESS = "IN_PROGRESS"
    REVIEW = "REVIEW"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class AssetScanResult(str, Enum):
    FOUND = "FOUND"
    MISSING = "MISSING"
    WRONG_LOCATION = "WRONG_LOCATION"
    WRONG_CUSTODIAN = "WRONG_CUSTODIAN"
    DAMAGED = "DAMAGED"
    UNREGISTERED = "UNREGISTERED"


class AssetDiscrepancyStatus(str, Enum):
    DETECTED = "DETECTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    APPROVED = "APPROVED"


# ── bajas (ASSET-12, §46-48) ─────────────────────────────────────────────────
class AssetDisposalReason(str, Enum):
    SALE = "SALE"
    DONATION = "DONATION"
    SCRAP = "SCRAP"
    LOSS = "LOSS"
    THEFT = "THEFT"
    OBSOLESCENCE = "OBSOLESCENCE"
    DAMAGE = "DAMAGE"
    REPLACEMENT = "REPLACEMENT"
    OTHER = "OTHER"


class AssetDisposalRequestStatus(str, Enum):
    REQUESTED = "REQUESTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


# ── etiquetas / QR (ASSET-13, §14, §49-51) ───────────────────────────────────
class AssetTagStatus(str, Enum):
    ISSUED = "ISSUED"
    PRINTED = "PRINTED"
    ACTIVE = "ACTIVE"
    REPLACED = "REPLACED"
    VOID = "VOID"


class AssetTagType(str, Enum):
    QR = "QR"
    BARCODE_128 = "BARCODE_128"
    DATA_MATRIX = "DATA_MATRIX"


# ── offline-first (ASSET-21, §105-106) — vocabulary only, see
# entities/asset_sync_conflict.py's module docstring for what is and is not
# actually wired up.
class AssetSyncStatus(str, Enum):
    LOCAL_PENDING = "LOCAL_PENDING"
    SYNCING = "SYNCING"
    SYNCED = "SYNCED"
    CONFLICT = "CONFLICT"
    FAILED = "FAILED"


class AssetSyncConflictType(str, Enum):
    ASSET_UPDATED_REMOTELY = "ASSET_UPDATED_REMOTELY"
    CUSTODY_CHANGED = "CUSTODY_CHANGED"
    LOCATION_CHANGED = "LOCATION_CHANGED"
    WORK_ORDER_CHANGED = "WORK_ORDER_CHANGED"
    DISPOSAL_STATE_CHANGED = "DISPOSAL_STATE_CHANGED"
    PHYSICAL_COUNT_CONFLICT = "PHYSICAL_COUNT_CONFLICT"


class AssetSyncConflictStatus(str, Enum):
    OPEN = "OPEN"
    RESOLVED_KEEP_LOCAL = "RESOLVED_KEEP_LOCAL"
    RESOLVED_KEEP_REMOTE = "RESOLVED_KEEP_REMOTE"
    RESOLVED_MERGED = "RESOLVED_MERGED"
