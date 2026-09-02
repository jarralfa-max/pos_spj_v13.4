"""Domain exceptions for the Loyalty Cards bounded context (LOY-1).

Loyalty Cards (physical/digital cards, templates, designer, sheet
imposition, batches, printing, QR) is its own specialized sub-bounded
context — master prompt §30: "El subdominio Tarjetas debe ser
especializado... La tarjeta no es la cuenta." It has its own nav entry
(``TARJETAS_FIDELIDAD``) and its own distinct segregation-of-duties roles
(§60: Diseñador de tarjetas, Aprobador de plantillas, Operador de
impresión), so it gets its own security foundation rather than sharing
``backend/domain/loyalty/exceptions.py``.

Mirrors ``backend/domain/sales/exceptions.py``'s SALES-2-equivalent phase.
"""

from __future__ import annotations


class LoyaltyCardDomainError(Exception):
    """Base for Loyalty Cards rule violations."""


class LoyaltyCardPermissionDeniedError(LoyaltyCardDomainError):
    """The user lacks the granular permission the action requires."""


class LoyaltyCardConfigurationError(LoyaltyCardDomainError):
    """A security-sensitive component was built without its mandatory
    wiring (e.g. an authorization policy with no PermissionChecker). Fail
    closed."""


class LoyaltyCardSegregationOfDutiesError(LoyaltyCardDomainError):
    """A hot authorization/approval was attempted by the same user who
    requested it (master prompt §60: 'quien diseña plantilla no la activa
    solo', 'quien genera lote no lo aprueba solo')."""


class InvalidLoyaltyCardAuditFieldError(LoyaltyCardDomainError):
    """A required audit/authorization field is missing or of the wrong
    type."""


# ── LOY-16: tarjeta base, token QR ──────────────────────────────────────

class InvalidLoyaltyCardError(LoyaltyCardDomainError):
    """A card's configuration is invalid (missing customer/membership,
    malformed card_number)."""


class LoyaltyCardNotFoundError(LoyaltyCardDomainError):
    """No LoyaltyCard with the given id/card_number exists."""


class InvalidLoyaltyCardStateError(LoyaltyCardDomainError):
    """The requested transition is not valid for the card's current
    status."""


class LoyaltyCardTokenNotFoundError(LoyaltyCardDomainError):
    """No LoyaltyCardPublicToken with the given id/token exists."""


class InvalidLoyaltyCardTokenStateError(LoyaltyCardDomainError):
    """The requested transition is not valid for the token's current
    status."""


# ── LOY-17: plantillas ──────────────────────────────────────────────────

class InvalidLoyaltyCardTemplateError(LoyaltyCardDomainError):
    """A template's configuration is invalid (missing code/name)."""


class LoyaltyCardTemplateNotFoundError(LoyaltyCardDomainError):
    """No LoyaltyCardTemplate with the given id/code exists."""


class InvalidLoyaltyCardTemplateStateError(LoyaltyCardDomainError):
    """The requested transition is not valid for the template's current
    status."""


class InvalidLoyaltyCardTemplateVersionError(LoyaltyCardDomainError):
    """A template version's configuration is invalid (missing/empty design
    schema)."""


class LoyaltyCardTemplateVersionNotFoundError(LoyaltyCardDomainError):
    """No LoyaltyCardTemplateVersion with the given id exists."""


class InvalidLoyaltyCardTemplateVersionStateError(LoyaltyCardDomainError):
    """The requested transition is not valid for the version's current
    status."""


# ── LOY-18: diseñador (esquema declarativo) ─────────────────────────────

class InvalidCardDesignSchemaError(LoyaltyCardDomainError):
    """`design_schema_json` violates the closed declarative vocabulary
    (§34-36: "no código ejecutable en las plantillas") — malformed JSON, an
    unknown element type/field, a disallowed placeholder token, or any HTML/
    script-like content. Fails closed; never sanitizes."""


# ── LOY-20: pliegos e imposición ────────────────────────────────────────

class InvalidSheetProfileError(LoyaltyCardDomainError):
    """A sheet profile's configuration is invalid (non-positive dimensions,
    margins that leave no printable area)."""


class LoyaltyCardSheetProfileNotFoundError(LoyaltyCardDomainError):
    """No LoyaltyCardSheetProfile with the given id exists."""


class InvalidImpositionProfileError(LoyaltyCardDomainError):
    """An imposition profile's configuration is invalid (non-positive card
    dimensions, safe_area_mm too large for the card, negative bleed/gutter)."""


class LoyaltyCardImpositionProfileNotFoundError(LoyaltyCardDomainError):
    """No LoyaltyCardImpositionProfile with the given id exists."""


class CardDoesNotFitOnSheetError(LoyaltyCardDomainError):
    """The card (plus bleed/gutter) is larger than the sheet's printable
    area — zero columns or rows would result."""


# ── LOY-21: lotes ────────────────────────────────────────────────────────

class InvalidLoyaltyCardBatchError(LoyaltyCardDomainError):
    """A batch's configuration is invalid (unavailable template, empty item
    list)."""


class LoyaltyCardBatchNotFoundError(LoyaltyCardDomainError):
    """No LoyaltyCardBatch with the given id exists."""


class InvalidLoyaltyCardBatchStateError(LoyaltyCardDomainError):
    """The requested transition is not valid for the batch's current
    status."""


class EmptyBatchError(LoyaltyCardDomainError):
    """A batch was attempted with zero items."""


class LoyaltyCardBatchItemNotFoundError(LoyaltyCardDomainError):
    """No LoyaltyCardBatchItem with the given id exists."""


class InvalidLoyaltyCardBatchItemStateError(LoyaltyCardDomainError):
    """The requested transition is not valid for the batch item's current
    status."""


# ── LOY-22: impresión ────────────────────────────────────────────────────

class InvalidLoyaltyCardPrintJobError(LoyaltyCardDomainError):
    """A print job's configuration is invalid (missing batch_id/requester)."""


class LoyaltyCardPrintJobNotFoundError(LoyaltyCardDomainError):
    """No LoyaltyCardPrintJob with the given id exists."""


class InvalidLoyaltyCardPrintJobStateError(LoyaltyCardDomainError):
    """The requested transition is not valid for the print job's current
    status."""


# ── LOY-23: tarjeta digital ──────────────────────────────────────────────

class InvalidDigitalCardProjectionError(LoyaltyCardDomainError):
    """A digital card projection's configuration is invalid (non-DIGITAL
    source card, missing display fields)."""


class DigitalCardProjectionNotFoundError(LoyaltyCardDomainError):
    """No LoyaltyDigitalCardProjection exists for the given card."""


class DigitalCardProjectionAlreadyExistsError(LoyaltyCardDomainError):
    """A LoyaltyDigitalCardProjection already exists for this card (one
    projection per card, §48)."""
