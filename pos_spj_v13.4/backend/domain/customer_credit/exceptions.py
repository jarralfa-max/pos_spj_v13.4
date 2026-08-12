"""Domain exceptions for the Customer Credit bounded context (CRM-8,
§37-40, §93).

Only this bounded context's own rule violations live here. Permission/
scope/SoD errors are NOT duplicated — Customer Credit reuses
``backend.application.customers.authorization.CustomerAuthorizationPolicy``,
``backend.application.customers.permissions.CustomerPermissions`` (the
``CREDIT_*`` codes already live there, CRM-2), and
``backend.domain.customers.policies.segregation_of_duties_policy.
CustomerSegregationOfDutiesPolicy`` (its
``enforce_credit_requester_not_self_approving`` was built in CRM-2
specifically for this phase and had no caller until now) directly — one
authorization/SoD stack for the whole Customer/CRM module, same reuse
CRM-7 already established for Service Cases against the ``crm`` stack.
Failures from those raise ``CustomerPermissionDeniedError``/
``CustomerScopeError``/``CustomerConfigurationError``/
``CustomerSegregationOfDutiesError`` (all ``backend.domain.customers.
exceptions``), never a parallel Customer-Credit-specific equivalent.
"""

from __future__ import annotations


class CustomerCreditDomainError(Exception):
    """Base for Customer Credit (profile/limit/eligibility) rule
    violations."""


class CustomerCreditProfileNotFoundError(CustomerCreditDomainError):
    """The customer has no credit profile (NOT_CONFIGURED — no row)."""


class InvalidCustomerCreditStateError(CustomerCreditDomainError):
    """A lifecycle transition is not valid from the profile's current
    status."""


class InvalidCustomerCreditProfileError(CustomerCreditDomainError):
    """A CustomerCreditProfile was built/updated with invalid data (e.g.
    non-positive limit, negative payment terms)."""
