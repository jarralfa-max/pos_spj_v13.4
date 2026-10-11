"""Errores del dominio de Cotizaciones (mensajes en español, se muestran tal cual)."""

from __future__ import annotations


class QuotesDomainError(Exception):
    code = "QUOTE_ERROR"


class QuoteValidationError(QuotesDomainError):
    code = "VALIDATION"


class InvalidQuoteStateError(QuotesDomainError):
    code = "INVALID_STATE"


class QuoteNotFoundError(QuotesDomainError):
    code = "NOT_FOUND"


class QuoteSegregationError(QuotesDomainError):
    code = "SEGREGATION"


class QuotePermissionDeniedError(QuotesDomainError):
    code = "PERMISSION_DENIED"


class QuotesConfigurationError(QuotesDomainError):
    code = "CONFIGURATION"
