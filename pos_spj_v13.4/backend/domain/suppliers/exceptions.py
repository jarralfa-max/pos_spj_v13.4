"""Domain exceptions for the suppliers bounded context."""

from __future__ import annotations


class SupplierDomainError(Exception):
    """Base for all supplier domain rule violations."""


class InvalidSupplierStateError(SupplierDomainError):
    pass


class SupplierAlreadyActiveError(SupplierDomainError):
    pass


class RejectedSupplierReactivationError(SupplierDomainError):
    pass


class SupplierCodeImmutableError(SupplierDomainError):
    pass


class DuplicateSupplierError(SupplierDomainError):
    pass


class SupplierBlockedError(SupplierDomainError):
    pass


class BankAccountNotVerifiedError(SupplierDomainError):
    pass


class SegregationOfDutiesError(SupplierDomainError):
    pass


class InvalidTaxIdentifierError(SupplierDomainError):
    pass


class InvalidSupplierCodeError(SupplierDomainError):
    pass


class InvalidCommercialTermsError(SupplierDomainError):
    pass


class InvalidEvaluationError(SupplierDomainError):
    pass


class SupplierDeletionForbiddenError(SupplierDomainError):
    pass


class PermissionDeniedError(SupplierDomainError):
    pass
