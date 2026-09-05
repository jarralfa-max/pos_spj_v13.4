"""Domain exceptions for the Assets / EAM bounded context (§108)."""

from __future__ import annotations


class AssetDomainError(Exception):
    """Base for asset/EAM rule violations."""


class AssetNotFoundError(AssetDomainError):
    pass


class AssetAlreadyExistsError(AssetDomainError):
    pass


class AssetStateInvalidError(AssetDomainError):
    """Requested transition is not valid from the asset's current status."""


class AssetConditionInvalidError(AssetDomainError):
    pass


class AssetCategoryNotFoundError(AssetDomainError):
    pass


class AssetLocationNotFoundError(AssetDomainError):
    pass


class AssetPermissionDeniedError(AssetDomainError):
    pass


class SegregationOfDutiesError(AssetDomainError):
    """Raised when a single user attempts both sides of a two-person control
    (e.g. requesting and approving their own disposal/authorization, §84)."""


class DuplicateOperationError(AssetDomainError):
    """An operation_id was already applied — the caller should treat the
    existing result as success rather than retry the mutation (§88)."""


class InvalidMoneyError(AssetDomainError):
    pass


# ── custodia / préstamos (ASSET-4, §108) ─────────────────────────────────────
class AssetAssignmentConflictError(AssetDomainError):
    """The asset is already actively assigned/loaned to someone else."""


class AssetLoanNotFoundError(AssetDomainError):
    pass


# ── transferencias (ASSET-5, §108) ───────────────────────────────────────────
class AssetTransferNotFoundError(AssetDomainError):
    pass


class AssetTransferNotAllowedError(AssetDomainError):
    """Requested transfer transition is not valid from its current status,
    or violates a segregation-of-duties rule (§84: quien solicita una
    transferencia no puede confirmar su propia recepción)."""


# ── mantenimiento (ASSET-6, §108) ────────────────────────────────────────────
class MaintenancePlanNotFoundError(AssetDomainError):
    pass


class MaintenanceWorkOrderNotFoundError(AssetDomainError):
    pass


class MaintenanceStateInvalidError(AssetDomainError):
    """Requested transition is not valid from the work order's current status."""


class MaintenanceCostInvalidError(AssetDomainError):
    pass


# ── inspecciones (ASSET-7, §108) ─────────────────────────────────────────────
class InspectionNotFoundError(AssetDomainError):
    pass


class InspectionFailedError(AssetDomainError):
    """Raised by workflows that need to react to a FAIL/OUT_OF_SERVICE result
    (e.g. CreateWorkOrderFromInspectionUseCase, a later application-layer phase)."""


class InspectionStateInvalidError(AssetDomainError):
    """A result was already recorded, or the checklist doesn't match."""


# ── medidores (ASSET-8, §108) ────────────────────────────────────────────────
class AssetMeterNotFoundError(AssetDomainError):
    pass


class MeterReadingInvalidError(AssetDomainError):
    """A meter reading must not go backwards (§39) unless the meter was
    explicitly reset — resets are a future concern, not modeled yet."""


# ── documentación / garantías / seguros (ASSET-9, §108) ─────────────────────
class AssetDocumentNotFoundError(AssetDomainError):
    pass


class AssetWarrantyNotFoundError(AssetDomainError):
    pass


class AssetInsuranceNotFoundError(AssetDomainError):
    pass


# ── costos / mejoras / capitalización propuesta (ASSET-10, §108) ────────────
class AssetImprovementNotFoundError(AssetDomainError):
    pass


class AssetCapitalizationProposalNotFoundError(AssetDomainError):
    pass


class AssetCapitalizationProposalInvalidError(AssetDomainError):
    """Requested transition is not valid from the proposal's current status."""


# ── inventario físico (ASSET-11, §108) ───────────────────────────────────────
class AssetPhysicalInventoryNotFoundError(AssetDomainError):
    pass


class AssetPhysicalInventoryConflictError(AssetDomainError):
    """Requested transition is not valid from the count's current status, or
    a line/discrepancy was already resolved."""


# ── bajas (ASSET-12, §108) ────────────────────────────────────────────────────
class AssetDisposalNotFoundError(AssetDomainError):
    pass


class AssetDisposalNotAllowedError(AssetDomainError):
    """Requested transition is not valid from the disposal request's current
    status, or violates a segregation-of-duties rule (§84: quien solicita una
    baja no debe aprobarla)."""


# ── etiquetas / QR (ASSET-13, §108) ──────────────────────────────────────────
class AssetTagNotFoundError(AssetDomainError):
    pass


class AssetTagDuplicateError(AssetDomainError):
    """A tag_number or qr_public_token collision — enforced by a UNIQUE
    constraint at the persistence layer (§88), guarded here at creation time
    for the in-memory/domain case."""


class AssetTagStateInvalidError(AssetDomainError):
    """Requested transition is not valid from the tag's current status."""


# ── integraciones (ASSET-15, §108) ───────────────────────────────────────────
class SupplierLookupUnavailableError(AssetDomainError):
    pass


class EmployeeLookupUnavailableError(AssetDomainError):
    pass


class DocumentStorageUnavailableError(AssetDomainError):
    pass


# ── offline-first (ASSET-21, §108) ───────────────────────────────────────────
class AssetSyncConflictNotFoundError(AssetDomainError):
    pass


class AssetSyncConflictAlreadyResolvedError(AssetDomainError):
    """A conflict record is never silently overwritten (§106) — resolving an
    already-resolved conflict is a programming error, not a valid retry."""
