"""Domain exceptions for the Customer Privacy bounded context (CRM-9,
§41-44, §93).

Only this bounded context's own rule violations live here. Permission/
scope/SoD errors are NOT duplicated — Customer Privacy reuses
``backend.application.customers.authorization.CustomerAuthorizationPolicy``,
``backend.application.customers.permissions.CustomerPermissions`` (the
``CONSENT_*``/``PRIVACY_REQUEST_*``/``SENSITIVE_DATA_*`` codes already live
there, CRM-2), and
``backend.domain.customers.policies.segregation_of_duties_policy.
CustomerSegregationOfDutiesPolicy`` (``enforce_anonymization_preserves_
audit`` was built in CRM-2 specifically for this phase and had no caller
until now) directly — same cross-package reuse discipline CRM-7/CRM-8
already established. Failures from those raise
``CustomerPermissionDeniedError``/``CustomerScopeError``/
``CustomerConfigurationError``/``CustomerSegregationOfDutiesError``/
``InvalidAuthorizationError`` (all ``backend.domain.customers.exceptions``),
never a parallel Customer-Privacy-specific equivalent.
"""

from __future__ import annotations


class CustomerPrivacyDomainError(Exception):
    """Base for Customer Privacy (consent/preference/request/retention)
    rule violations."""


class CustomerConsentNotFoundError(CustomerPrivacyDomainError):
    """Referenced a consent record that does not exist."""


class InvalidCustomerConsentStateError(CustomerPrivacyDomainError):
    """A consent lifecycle transition is not valid from its current
    status."""


class CommunicationPreferenceNotFoundError(CustomerPrivacyDomainError):
    """The customer has no communication preference record configured."""


class PrivacyRequestNotFoundError(CustomerPrivacyDomainError):
    """Referenced a privacy request that does not exist."""


class InvalidPrivacyRequestStateError(CustomerPrivacyDomainError):
    """A privacy request lifecycle transition is not valid from its
    current status."""


class InvalidPrivacyRequestCodeError(CustomerPrivacyDomainError):
    """A PrivacyRequestCode (folio) does not match the canonical
    PRIV-NNNNNN shape."""


class InvalidDataRetentionPolicyError(CustomerPrivacyDomainError):
    """A CustomerDataRetentionPolicy was built with invalid configuration
    (e.g. non-positive retention_days)."""
