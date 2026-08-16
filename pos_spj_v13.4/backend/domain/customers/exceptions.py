"""Domain exceptions for the Customer Master bounded context.

CRM-2 (§59-76) added the security-error shape, mirroring
backend/domain/inventory/exceptions.py: an unconfigured authorization gate
never allows, a missing session/actor never allows, two conflicting duties
held by the same user never allow. CRM-3 (§12-15, §93) adds the entity/
value-object errors — state transitions, uniqueness, malformed value
objects — mirroring backend/domain/suppliers/exceptions.py.
"""

from __future__ import annotations


class CustomerDomainError(Exception):
    """Base for Customer Master rule violations."""


class CustomerPermissionDeniedError(CustomerDomainError):
    """The user lacks the granular permission the action requires."""


class CustomerConfigurationError(CustomerDomainError):
    """A security-sensitive component was built without its mandatory wiring
    (e.g. an authorization policy with no PermissionChecker, or a scope
    resolver with no session). Fail closed: never allow an operation to
    proceed on an unconfigured authorization gate."""


class CustomerAuthenticationRequiredError(CustomerDomainError):
    """No authenticated session — the operation cannot resolve an actor."""

    code = "AUTHENTICATION_REQUIRED"


class CustomerScopeError(CustomerDomainError):
    """The user's granted data scope (OWN/TEAM/BRANCH/TERRITORY/PORTFOLIO/
    COMPANY) does not cover the requested customer/branch/territory/portfolio."""


class CustomerSegregationOfDutiesError(CustomerDomainError):
    """The same user cannot hold two conflicting roles in one operation
    (credit requester/approver, merge proposer/approver, sensitive-import
    submitter/approver, ...)."""


class InvalidAuthorizationError(CustomerDomainError):
    """An authorization grant or audit entry was built with missing/invalid
    required fields."""


# ── CRM-3: entities and value objects (§12-15, §93) ─────────────────────────

class CustomerNotFoundError(CustomerDomainError):
    """Referenced a customer_id/entity_id that does not exist."""


class CustomerAlreadyExistsError(CustomerDomainError):
    """A customer_number or operation_id collision on create."""


class InvalidCustomerStateError(CustomerDomainError):
    """A lifecycle transition (activate/suspend/block/close) is not valid
    from the customer's current status."""


class CustomerBlockedError(CustomerDomainError):
    """An operation was attempted against a BLOCKED/CLOSED customer."""


class CustomerDuplicateDetectedError(CustomerDomainError):
    """A likely-duplicate customer was found and the caller did not
    explicitly opt to create anyway (§45)."""


class InvalidCustomerCodeError(CustomerDomainError):
    """A CustomerCode (folio) does not match the canonical CLI-NNNNNN shape."""


class InvalidPhoneNumberError(CustomerDomainError):
    """A phone value does not normalize to a valid E.164 number."""


class InvalidEmailAddressError(CustomerDomainError):
    """An email value is not a syntactically valid address."""


# ── CRM-11: Calidad, duplicados, fusión, importación (§45-47, §73-74) ───────

class CustomerDuplicateCandidateNotFoundError(CustomerDomainError):
    """Referenced a duplicate_candidate_id that does not exist."""


class InvalidDuplicateCandidateStateError(CustomerDomainError):
    """A lifecycle transition (review/confirm/dismiss) is not valid from the
    candidate's current status."""


class CustomerMergeRecordNotFoundError(CustomerDomainError):
    """Referenced a merge_record_id that does not exist."""


class InvalidCustomerMergeStateError(CustomerDomainError):
    """A lifecycle transition (execute/reject) is not valid from the merge
    record's current status, or the merge was proposed with an invalid
    master/merged pair (e.g. the same customer twice)."""


class CustomerDataQualityIssueNotFoundError(CustomerDomainError):
    """Referenced a data_quality_issue_id that does not exist."""


class InvalidDataQualityIssueStateError(CustomerDomainError):
    """A lifecycle transition (acknowledge/correct/dismiss) is not valid
    from the issue's current status."""


class CustomerImportBatchNotFoundError(CustomerDomainError):
    """Referenced an import_batch_id that does not exist."""


class InvalidCustomerImportError(CustomerDomainError):
    """An import batch/row was built or transitioned invalidly (e.g. no
    rows, or approving a batch that isn't pending approval)."""


# ── CRM-20: Offline-first sync conflicts (§91-92) ────────────────────────────

class CustomerSyncConflictNotFoundError(CustomerDomainError):
    """Referenced a sync conflict_id that does not exist."""


class CustomerSyncConflictAlreadyResolvedError(CustomerDomainError):
    """Attempted to resolve or re-detect a conflict that is no longer OPEN."""


class CustomerSyncConflictDetectedError(CustomerDomainError):
    """§92: "no sobrescribir silenciosamente" — raised (never silently
    swallowed) when an incoming remote mutation targets a stale local
    version. The caller must not apply the incoming change; a
    CustomerSyncConflict record blocks it until explicitly resolved."""
