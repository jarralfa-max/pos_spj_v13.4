"""Domain exceptions for the Customer Service (atención al cliente) bounded
context (CRM-7, §30-32, §93).

Only this bounded context's own rule violations live here. Permission/
scope/configuration errors are NOT duplicated here — Customer Service
reuses ``backend.application.crm.authorization.CRMAuthorizationPolicy`` and
``backend.application.crm.data_scope.CRMDataScopeResolver`` directly
(CRM-2 built one authorization stack for the whole Leads/Opportunities/
Activities/Cases family; ``CASES_*``/``SLA_*`` permissions already live in
``CRMPermissions``), so those failures raise
``backend.domain.crm.exceptions.CRMPermissionDeniedError``/
``CRMScopeError``/``CRMConfigurationError`` — never a parallel
``CustomerServicePermissionDeniedError`` that would just be the same
concept under a different name.
"""

from __future__ import annotations


class CustomerServiceDomainError(Exception):
    """Base for Customer Service (case/SLA) rule violations."""


class ServiceCaseNotFoundError(CustomerServiceDomainError):
    """Referenced a case_id that does not exist."""


class InvalidServiceCaseStateError(CustomerServiceDomainError):
    """A lifecycle transition is not valid from the case's current status."""


class InvalidServiceCaseCodeError(CustomerServiceDomainError):
    """A ServiceCaseCode (folio) does not match the canonical CASE-NNNNNN
    shape."""


class InvalidServiceCaseCategoryError(CustomerServiceDomainError):
    """A ServiceCaseCategory was built with invalid configuration."""


class InvalidServiceCaseResolutionError(CustomerServiceDomainError):
    """A ServiceCaseResolution was built with missing/invalid content."""


class InvalidServiceLevelPolicyError(CustomerServiceDomainError):
    """A ServiceLevelPolicy was built with invalid configuration (e.g.
    non-positive minutes, out-of-range at-risk threshold)."""


class InvalidSLAInstanceError(CustomerServiceDomainError):
    """An SLAInstance operation is not valid given its current state (e.g.
    recording a first response twice)."""


class SLAInstanceNotFoundError(CustomerServiceDomainError):
    """Referenced an sla_instance for a case that has none."""
