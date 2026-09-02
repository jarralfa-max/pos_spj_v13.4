"""SweepstakesResult — the return type every Sweepstakes use case produces.
Mirrors backend/application/commercial_instruments/result.py's shape
exactly."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.domain.loyalty.exceptions import (
    LoyaltyConfigurationError,
    LoyaltyPermissionDeniedError,
)
from backend.domain.sweepstakes.exceptions import (
    DuplicateWinnerTicketError,
    EmptyTicketPoolError,
    InvalidSweepstakesCampaignError,
    InvalidSweepstakesCampaignStateError,
    InvalidSweepstakesDrawStateError,
    InvalidSweepstakesEntryError,
    InvalidSweepstakesPrizeError,
    InvalidSweepstakesRuleError,
    InvalidSweepstakesTicketStateError,
    InvalidSweepstakesWinnerStateError,
    SweepstakesCampaignNotFoundError,
    SweepstakesDomainError,
    SweepstakesDrawNotFoundError,
    SweepstakesEntryNotFoundError,
    SweepstakesPrizeNotFoundError,
    SweepstakesRuleNotFoundError,
    SweepstakesTicketNotFoundError,
    SweepstakesWinnerNotFoundError,
    TicketRequiresExistingEntryError,
)


@dataclass(frozen=True, slots=True)
class SweepstakesResult:
    success: bool
    message: str = ""
    operation_id: str | None = None
    entity_id: str | None = None
    error_code: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, message: str = "", *, entity_id: str | None = None,
           operation_id: str | None = None, **data: Any) -> "SweepstakesResult":
        return cls(True, message, operation_id, entity_id, None, dict(data))

    @classmethod
    def fail(cls, message: str, error_code: str, *,
             operation_id: str | None = None, **data: Any) -> "SweepstakesResult":
        return cls(False, message, operation_id, None, error_code, dict(data))


_ERROR_CODES: tuple[tuple[type[Exception], str], ...] = (
    (LoyaltyPermissionDeniedError, "PERMISSION_DENIED"),
    (LoyaltyConfigurationError, "CONFIGURATION_ERROR"),
    (SweepstakesCampaignNotFoundError, "CAMPAIGN_NOT_FOUND"),
    (InvalidSweepstakesCampaignError, "INVALID_CAMPAIGN"),
    (InvalidSweepstakesCampaignStateError, "CAMPAIGN_INVALID_STATE"),
    (SweepstakesRuleNotFoundError, "RULE_NOT_FOUND"),
    (InvalidSweepstakesRuleError, "INVALID_RULE"),
    (SweepstakesPrizeNotFoundError, "PRIZE_NOT_FOUND"),
    (InvalidSweepstakesPrizeError, "INVALID_PRIZE"),
    (SweepstakesEntryNotFoundError, "ENTRY_NOT_FOUND"),
    (InvalidSweepstakesEntryError, "INVALID_ENTRY"),
    (TicketRequiresExistingEntryError, "TICKET_REQUIRES_ENTRY"),
    (SweepstakesTicketNotFoundError, "TICKET_NOT_FOUND"),
    (InvalidSweepstakesTicketStateError, "TICKET_INVALID_STATE"),
    (SweepstakesDrawNotFoundError, "DRAW_NOT_FOUND"),
    (InvalidSweepstakesDrawStateError, "DRAW_INVALID_STATE"),
    (EmptyTicketPoolError, "EMPTY_TICKET_POOL"),
    (SweepstakesWinnerNotFoundError, "WINNER_NOT_FOUND"),
    (InvalidSweepstakesWinnerStateError, "WINNER_INVALID_STATE"),
    (DuplicateWinnerTicketError, "DUPLICATE_WINNER_TICKET"),
)


def fail_from_domain_error(
    exc: SweepstakesDomainError | Exception, *, operation_id: str | None = None,
) -> SweepstakesResult:
    """Translate any typed domain exception (Sweepstakes' own, or a shared
    LOY-1 security exception reused via `LoyaltyAuthorizationPolicy`) into a
    `SweepstakesResult.fail()`."""
    code = next((code for cls, code in _ERROR_CODES if isinstance(exc, cls)), "VALIDATION")
    return SweepstakesResult.fail(str(exc), code, operation_id=operation_id)
