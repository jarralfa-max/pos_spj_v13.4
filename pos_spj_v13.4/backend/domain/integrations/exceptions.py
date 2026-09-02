"""Domain exceptions for the Integrations bounded context — SET-19.
Mirrors backend/domain/customer_display/exceptions.py's shape.
"""

from __future__ import annotations


class IntegrationsDomainError(Exception):
    """Base for Integrations rule violations."""


class IntegrationsInvalidValueError(IntegrationsDomainError):
    """A field does not satisfy its validation rule."""


class IntegrationDefinitionNotFoundError(IntegrationsDomainError):
    """Referenced an `IntegrationDefinition` id/code that does not
    exist."""


class IntegrationInstanceNotFoundError(IntegrationsDomainError):
    """Referenced an `IntegrationInstance` id that does not exist."""


class MissingCredentialError(IntegrationsDomainError):
    """An `IntegrationInstance` is missing a credential reference its
    `IntegrationDefinition` requires (§ "Credentials")."""


class WebhookEndpointNotFoundError(IntegrationsDomainError):
    """Referenced a `WebhookEndpoint` id/code that does not exist."""
