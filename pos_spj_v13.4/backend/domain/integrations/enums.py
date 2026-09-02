"""Canonical enums for the Integrations bounded context — SET-19. See
docs/refactor/settings_refactor_execution_plan.md. Governs external
integration catalog/instances/credentials/health/webhooks for the ERP —
WhatsApp (§14 of CLAUDE.md, its 3 legacy shims preserved untouched) and
MercadoPago (webhook signature verification already real and live since
SET-1) are the two integrations this generalizes from, not invents.
"""

from __future__ import annotations

from enum import Enum


class IntegrationCategory(str, Enum):
    """"Definitions": what kind of external system an
    `IntegrationDefinition` describes."""

    MESSAGING = "MESSAGING"
    PAYMENTS = "PAYMENTS"
    FISCAL = "FISCAL"
    LOCATION = "LOCATION"
    EMAIL = "EMAIL"
    SMS = "SMS"
    OTHER = "OTHER"


class IntegrationHealthStatus(str, Enum):
    """"Health": the status `policies/integration_health_policy.py::
    current_status()` derives from an `IntegrationInstance`'s recent
    `IntegrationHealthCheck` history."""

    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"


class WebhookSignatureScheme(str, Enum):
    """"Webhooks": which signature-verification scheme a
    `WebhookEndpoint` uses. Generalizes the two real, live schemes
    already implemented in `whatsapp_service/middleware/hmac_validator.py`
    (`verify_signature` for Meta's `X-Hub-Signature-256`,
    `verify_mp_signature` for MercadoPago's `ts=...,v1=...` manifest) —
    this bounded context never imports that module directly (WhatsApp is
    a separate, independently-deployed microservice per CLAUDE.md §14),
    but a real verifier
    (`backend/infrastructure/integrations/webhook_signature_verifier.py`)
    faithfully reimplements the same two well-specified, stateless HMAC
    schemes on this side of the service boundary — see that module's
    docstring."""

    HMAC_SHA256_HEADER = "HMAC_SHA256_HEADER"
    MERCADOPAGO_TS_V1 = "MERCADOPAGO_TS_V1"
    NONE = "NONE"
