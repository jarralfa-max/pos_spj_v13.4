"""Domain exceptions for the Sweepstakes/Sorteos bounded context (LOY-15,
master prompt §27-28)."""

from __future__ import annotations


class SweepstakesDomainError(Exception):
    """Base for Sweepstakes rule violations."""


class InvalidSweepstakesCampaignError(SweepstakesDomainError):
    """A campaign's configuration is invalid (missing code/name, non-positive
    ticket_price where required, non-Decimal amounts)."""


class SweepstakesCampaignNotFoundError(SweepstakesDomainError):
    """No SweepstakesCampaign with the given id exists."""


class InvalidSweepstakesCampaignStateError(SweepstakesDomainError):
    """The requested transition is not valid for the campaign's current
    status."""


class InvalidSweepstakesRuleError(SweepstakesDomainError):
    """A rule's configuration is invalid (e.g. non-positive
    amount_per_ticket for a PURCHASE_AMOUNT strategy)."""


class SweepstakesRuleNotFoundError(SweepstakesDomainError):
    """No SweepstakesRule exists for the given campaign."""


class InvalidSweepstakesPrizeError(SweepstakesDomainError):
    """A prize's configuration is invalid (missing name, non-positive
    quantity)."""


class SweepstakesPrizeNotFoundError(SweepstakesDomainError):
    """No SweepstakesPrize with the given id exists."""


class InvalidSweepstakesEntryError(SweepstakesDomainError):
    """An entry's configuration is invalid (missing customer/source, a
    non-positive chances_granted)."""


class SweepstakesEntryNotFoundError(SweepstakesDomainError):
    """No SweepstakesEntry with the given id exists — required to exist
    BEFORE any ticket referencing it can be issued (§28)."""


class SweepstakesTicketNotFoundError(SweepstakesDomainError):
    """No SweepstakesTicket with the given id/number exists."""


class InvalidSweepstakesTicketStateError(SweepstakesDomainError):
    """The requested transition is not valid for the ticket's current
    status."""


class TicketRequiresExistingEntryError(SweepstakesDomainError):
    """§28: 'No debe existir boleto sin folio/derecho previo' — a ticket can
    never be issued without a real, already-persisted SweepstakesEntry in
    the same campaign."""


class SweepstakesDrawNotFoundError(SweepstakesDomainError):
    """No SweepstakesDraw with the given id exists."""


class InvalidSweepstakesDrawStateError(SweepstakesDomainError):
    """The requested transition is not valid for the draw's current status."""


class EmptyTicketPoolError(SweepstakesDomainError):
    """A draw was attempted with zero eligible tickets in the pool."""


class SweepstakesWinnerNotFoundError(SweepstakesDomainError):
    """No SweepstakesWinner with the given id exists."""


class InvalidSweepstakesWinnerStateError(SweepstakesDomainError):
    """The requested transition is not valid for the winner record's
    current status."""


class DuplicateWinnerTicketError(SweepstakesDomainError):
    """The same ticket was already selected as a winner in this draw."""
