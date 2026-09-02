"""Canonical enums for the Sweepstakes/Sorteos bounded context (LOY-15,
master prompt §27-28, §7.2). Separate package from ``backend.domain.loyalty``
and from the legacy ``raffle_*`` tables (``migrations/standalone/113_raffle_
subsystem.py``) — a sweepstakes/rifa is a distinct promotional mechanism
with its own lifecycle, not a loyalty-owned concept, even though it shares
the same ``GROWTH_ENGINE`` permission surface
(``LoyaltyPermissions.SWEEPSTAKES_*``, already defined in LOY-1)."""

from __future__ import annotations

from enum import Enum


class SweepstakesCampaignStatus(str, Enum):
    """§27."""
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DRAWN = "DRAWN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class SweepstakesEntryMethod(str, Enum):
    """§27 — how a customer earns entries/chances."""
    PURCHASE_AMOUNT = "PURCHASE_AMOUNT"
    PRODUCT_PURCHASE = "PRODUCT_PURCHASE"
    MANUAL_GRANT = "MANUAL_GRANT"
    REFERRAL = "REFERRAL"
    LOYALTY_POINTS_EXCHANGE = "LOYALTY_POINTS_EXCHANGE"


class SweepstakesTicketStatus(str, Enum):
    """§28 — a ticket is always ISSUED from a pre-existing entry; PRINTED
    records that physical/digital output happened at least once (reprints
    keep the same ticket row, see `SweepstakesTicket.record_print()`)."""
    ISSUED = "ISSUED"
    PRINTED = "PRINTED"
    VOID = "VOID"


class SweepstakesDrawStatus(str, Enum):
    """§27."""
    SCHEDULED = "SCHEDULED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class SweepstakesWinnerStatus(str, Enum):
    """§27."""
    PENDING_VALIDATION = "PENDING_VALIDATION"
    VALIDATED = "VALIDATED"
    DISQUALIFIED = "DISQUALIFIED"
    PRIZE_DELIVERED = "PRIZE_DELIVERED"
    EXPIRED = "EXPIRED"


class SweepstakesPrizeStatus(str, Enum):
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    DELIVERED = "DELIVERED"
