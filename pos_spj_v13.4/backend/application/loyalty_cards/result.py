"""LoyaltyCardResult — the return type every Loyalty Cards use case
produces. Mirrors backend/application/sweepstakes/result.py's shape
exactly."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.domain.loyalty_cards.exceptions import (
    CardDoesNotFitOnSheetError,
    DigitalCardProjectionAlreadyExistsError,
    DigitalCardProjectionNotFoundError,
    EmptyBatchError,
    InvalidDigitalCardProjectionError,
    InvalidCardDesignSchemaError,
    InvalidImpositionProfileError,
    InvalidLoyaltyCardAuditFieldError,
    InvalidLoyaltyCardBatchError,
    InvalidLoyaltyCardBatchItemStateError,
    InvalidLoyaltyCardBatchStateError,
    InvalidLoyaltyCardError,
    InvalidLoyaltyCardPrintJobError,
    InvalidLoyaltyCardPrintJobStateError,
    InvalidLoyaltyCardStateError,
    InvalidLoyaltyCardTemplateError,
    InvalidLoyaltyCardTemplateStateError,
    InvalidLoyaltyCardTemplateVersionError,
    InvalidLoyaltyCardTemplateVersionStateError,
    InvalidLoyaltyCardTokenStateError,
    InvalidSheetProfileError,
    LoyaltyCardBatchItemNotFoundError,
    LoyaltyCardBatchNotFoundError,
    LoyaltyCardConfigurationError,
    LoyaltyCardDomainError,
    LoyaltyCardImpositionProfileNotFoundError,
    LoyaltyCardNotFoundError,
    LoyaltyCardPermissionDeniedError,
    LoyaltyCardPrintJobNotFoundError,
    LoyaltyCardSegregationOfDutiesError,
    LoyaltyCardSheetProfileNotFoundError,
    LoyaltyCardTemplateNotFoundError,
    LoyaltyCardTemplateVersionNotFoundError,
    LoyaltyCardTokenNotFoundError,
)


@dataclass(frozen=True, slots=True)
class LoyaltyCardResult:
    success: bool
    message: str = ""
    operation_id: str | None = None
    entity_id: str | None = None
    error_code: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, message: str = "", *, entity_id: str | None = None,
           operation_id: str | None = None, **data: Any) -> "LoyaltyCardResult":
        return cls(True, message, operation_id, entity_id, None, dict(data))

    @classmethod
    def fail(cls, message: str, error_code: str, *,
             operation_id: str | None = None, **data: Any) -> "LoyaltyCardResult":
        return cls(False, message, operation_id, None, error_code, dict(data))


_ERROR_CODES: tuple[tuple[type[Exception], str], ...] = (
    (LoyaltyCardPermissionDeniedError, "PERMISSION_DENIED"),
    (LoyaltyCardConfigurationError, "CONFIGURATION_ERROR"),
    (LoyaltyCardSegregationOfDutiesError, "SEGREGATION_OF_DUTIES"),
    (InvalidLoyaltyCardAuditFieldError, "INVALID_AUDIT_FIELD"),
    (LoyaltyCardNotFoundError, "CARD_NOT_FOUND"),
    (InvalidLoyaltyCardError, "INVALID_CARD"),
    (InvalidLoyaltyCardStateError, "CARD_INVALID_STATE"),
    (LoyaltyCardTokenNotFoundError, "TOKEN_NOT_FOUND"),
    (InvalidLoyaltyCardTokenStateError, "TOKEN_INVALID_STATE"),
    (LoyaltyCardTemplateNotFoundError, "TEMPLATE_NOT_FOUND"),
    (InvalidLoyaltyCardTemplateError, "INVALID_TEMPLATE"),
    (InvalidLoyaltyCardTemplateStateError, "TEMPLATE_INVALID_STATE"),
    (LoyaltyCardTemplateVersionNotFoundError, "TEMPLATE_VERSION_NOT_FOUND"),
    (InvalidLoyaltyCardTemplateVersionError, "INVALID_TEMPLATE_VERSION"),
    (InvalidLoyaltyCardTemplateVersionStateError, "TEMPLATE_VERSION_INVALID_STATE"),
    (InvalidCardDesignSchemaError, "INVALID_DESIGN_SCHEMA"),
    (LoyaltyCardSheetProfileNotFoundError, "SHEET_PROFILE_NOT_FOUND"),
    (InvalidSheetProfileError, "INVALID_SHEET_PROFILE"),
    (LoyaltyCardImpositionProfileNotFoundError, "IMPOSITION_PROFILE_NOT_FOUND"),
    (InvalidImpositionProfileError, "INVALID_IMPOSITION_PROFILE"),
    (CardDoesNotFitOnSheetError, "CARD_DOES_NOT_FIT_ON_SHEET"),
    (LoyaltyCardBatchNotFoundError, "BATCH_NOT_FOUND"),
    (EmptyBatchError, "EMPTY_BATCH"),
    (InvalidLoyaltyCardBatchError, "INVALID_BATCH"),
    (InvalidLoyaltyCardBatchStateError, "BATCH_INVALID_STATE"),
    (LoyaltyCardBatchItemNotFoundError, "BATCH_ITEM_NOT_FOUND"),
    (InvalidLoyaltyCardBatchItemStateError, "BATCH_ITEM_INVALID_STATE"),
    (LoyaltyCardPrintJobNotFoundError, "PRINT_JOB_NOT_FOUND"),
    (InvalidLoyaltyCardPrintJobStateError, "PRINT_JOB_INVALID_STATE"),
    (InvalidLoyaltyCardPrintJobError, "INVALID_PRINT_JOB"),
    (DigitalCardProjectionNotFoundError, "DIGITAL_PROJECTION_NOT_FOUND"),
    (DigitalCardProjectionAlreadyExistsError, "DIGITAL_PROJECTION_ALREADY_EXISTS"),
    (InvalidDigitalCardProjectionError, "INVALID_DIGITAL_PROJECTION"),
)


def fail_from_domain_error(
    exc: LoyaltyCardDomainError | Exception, *, operation_id: str | None = None,
) -> LoyaltyCardResult:
    code = next((code for cls, code in _ERROR_CODES if isinstance(exc, cls)), "VALIDATION")
    return LoyaltyCardResult.fail(str(exc), code, operation_id=operation_id)
