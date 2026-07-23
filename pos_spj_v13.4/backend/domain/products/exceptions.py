"""Domain exceptions for the products bounded context.

PROD-1 defines the security-related errors (permission, hot authorization,
segregation of duties, scope, duplicate operation). Later phases add the
operational errors from §47 (ProductNotFoundError, InvalidMeatClassificationError,
RecipeCycleDetectedError, YieldProfileInvalidError, …) next to these.
"""

from __future__ import annotations


class ProductsDomainError(Exception):
    """Base for products rule violations."""


class ProductPermissionDeniedError(ProductsDomainError):
    """The user lacks the granular permission the action requires."""


class ProductAuthorizationRequiredError(ProductsDomainError):
    """Not an outright denial — the operation needs a hot authorization."""


class SegregationOfDutiesError(ProductsDomainError):
    """The same user cannot hold two conflicting roles in one operation.

    §39: whoever creates a recipe/yield/import must not approve or activate it
    when the policy demands a second pair of eyes.
    """


class BranchScopeError(ProductsDomainError):
    """The user may not operate on the requested branch."""


class ProductTypeScopeError(ProductsDomainError):
    """The user may not operate on the requested product type.

    Internal / meat / cost-reference views are gated by their own permissions
    (§37-38); a user without them may not read or mutate those products.
    """


class DuplicateOperationError(ProductsDomainError):
    """An operation_id was replayed (idempotency guard)."""


class InvalidAuthorizationError(ProductsDomainError):
    """A hot authorization or audit entry was built with invalid/missing data."""


# ── PROD-2 Product Master ────────────────────────────────────────────────────
class ProductNotFoundError(ProductsDomainError):
    """No product exists for the given id/code."""


class ProductAlreadyExistsError(ProductsDomainError):
    """A product with the same code/barcode already exists."""


class InvalidProductTypeError(ProductsDomainError):
    """An unknown or inconsistent product type was supplied."""


class InvalidProductStateError(ProductsDomainError):
    """A lifecycle transition is not allowed from the current state."""


class ProductInactiveError(ProductsDomainError):
    """The product is not ACTIVE and cannot be used for the requested operation."""


class ProductDiscontinuedError(ProductsDomainError):
    """The product is DISCONTINUED/ARCHIVED and cannot be reactivated in place."""


class ProductIncompleteError(ProductsDomainError):
    """The product cannot be activated while required master data is missing (§7)."""


class SpeciesRequiredError(ProductsDomainError):
    """A meat product type was created without a species (§7, §11)."""


# ── PROD-5 units / conversions / catch weight ────────────────────────────────
class InvalidUnitOfMeasureError(ProductsDomainError):
    """A unit of measure was defined with a missing/invalid code or dimension."""


class InvalidUnitConversionError(ProductsDomainError):
    """A conversion has a non-positive factor, mixes float, or is malformed."""


class UnitConversionCycleError(ProductsDomainError):
    """The conversion graph would contain a cycle (§16)."""


class UnitConversionNotFoundError(ProductsDomainError):
    """No conversion path exists between the requested units."""


class InvalidCatchWeightConfigurationError(ProductsDomainError):
    """A catch-weight configuration has an invalid range/tolerance/price basis (§12)."""


# ── PROD-7 barcodes / codes / labels ─────────────────────────────────────────
class InvalidBarcodeError(ProductsDomainError):
    """A barcode is empty, malformed, or fails its checksum (§17)."""


class BarcodeAlreadyAssignedError(ProductsDomainError):
    """An active barcode is already assigned to another product (§17 uniqueness)."""


class InvalidScaleBarcodeError(ProductsDomainError):
    """A scale barcode does not match the configured embedded-weight format (§12)."""


# ── PROD-8 quality / shelf life / logistics ──────────────────────────────────
class InvalidTemperatureRangeError(ProductsDomainError):
    """A temperature range is malformed (min > max, float, missing unit) (§18)."""


class InvalidShelfLifeProfileError(ProductsDomainError):
    """A shelf-life profile has invalid day values or window (§19)."""


class ShelfLifeRequiredError(ProductsDomainError):
    """A perishable product was activated without a shelf-life profile (§19, §35)."""


class InvalidQualityProfileError(ProductsDomainError):
    """A quality profile has an invalid percentage/range (§20)."""


# ── PROD-9 recipes / BOM ─────────────────────────────────────────────────────
class InvalidRecipeError(ProductsDomainError):
    """A recipe/version/component/output is malformed (§21)."""


class RecipeCycleDetectedError(ProductsDomainError):
    """A recipe would consume its own output directly or transitively (§21)."""


class RecipeYieldInvalidError(ProductsDomainError):
    """A recipe output yield/quantity is invalid (§21)."""


class RecipeVersionImmutableError(ProductsDomainError):
    """An ACTIVE/APPROVED recipe version cannot be modified in place (§22)."""


class NoActiveRecipeVersionError(ProductsDomainError):
    """No ACTIVE version exists for the requested recipe."""


# ── PROD-10 yield profiles ───────────────────────────────────────────────────
class YieldProfileInvalidError(ProductsDomainError):
    """A yield profile/version/output is malformed (§23)."""


class YieldToleranceExceededError(ProductsDomainError):
    """The declared outputs do not sum within the configured tolerance (§23)."""
