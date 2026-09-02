"""Domain exceptions for the Fidelidad/Loyalty bounded context.

LOY-1 defined the security-related errors (permission, configuration, hot
authorization, segregation of duties) for the whole "Fidelización" area —
programs, memberships, points ledger, tiers, rewards, challenges, referrals,
birthdays, retention, campaigns, coupons, vouchers and sweepstakes/raffles
(master prompt §4: they all share one nav entry/permission catalog key,
``GROWTH_ENGINE``). Loyalty Cards is a separate, specialized sub-bounded
context with its own nav entry and its own exceptions
(``backend/domain/loyalty_cards/exceptions.py``).
LOY-2 adds the operational errors the Program/Account/Membership/Transaction
entities and the ledger balance policy raise (master prompt §66, the subset
a pure domain layer can detect without I/O).

Mirrors ``backend/domain/sales/exceptions.py``'s own SALES-2/3-equivalent
phases exactly.
"""

from __future__ import annotations


class LoyaltyDomainError(Exception):
    """Base for Fidelidad/Loyalty rule violations."""


class LoyaltyPermissionDeniedError(LoyaltyDomainError):
    """The user lacks the granular permission the action requires."""


class LoyaltyConfigurationError(LoyaltyDomainError):
    """A security-sensitive component was built without its mandatory
    wiring (e.g. an authorization policy with no PermissionChecker). Fail
    closed: never allow an operation to proceed on an unconfigured
    authorization gate."""


class LoyaltySegregationOfDutiesError(LoyaltyDomainError):
    """A hot authorization/approval was attempted by the same user who
    requested it — a second pair of eyes is mandatory (master prompt §60:
    'quien ajusta puntos no aprueba su propio ajuste', 'quien crea campaña
    no la activa solo')."""


class InvalidLoyaltyAuditFieldError(LoyaltyDomainError):
    """A required audit/authorization field is missing or of the wrong
    type (e.g. a float where Decimal is required)."""


# ── LOY-2: operational errors (master prompt §66, domain-detectable subset) ──

class LoyaltyProgramNotFoundError(LoyaltyDomainError):
    """No LoyaltyProgram with the given id exists (master prompt §66)."""


class InvalidLoyaltyProgramStateError(LoyaltyDomainError):
    """The requested transition is not valid for the program's current
    status, or a required field (code/name/currency_name) is missing."""


class LoyaltyProgramInactiveError(LoyaltyDomainError):
    """An operation that requires an ACTIVE program (enroll, accrue,
    redeem) was attempted against a program that is not ACTIVE."""


class LoyaltyAccountNotFoundError(LoyaltyDomainError):
    """No LoyaltyAccount with the given id/customer_id exists."""


class InvalidLoyaltyAccountStateError(LoyaltyDomainError):
    """The requested transition is not valid for the account's current
    status."""


class LoyaltyAccountSuspendedError(LoyaltyDomainError):
    """An operation that requires an ACTIVE account was attempted against a
    suspended/closed one."""


class LoyaltyMembershipNotFoundError(LoyaltyDomainError):
    """No LoyaltyMembership with the given id exists."""


class InvalidLoyaltyMembershipStateError(LoyaltyDomainError):
    """The requested transition is not valid for the membership's current
    status."""


class InvalidLoyaltyTransactionAmountError(LoyaltyDomainError):
    """``points_amount`` is missing, non-Decimal, zero, or has the wrong
    sign for its ``transaction_type`` (e.g. a negative EARN)."""


class InvalidLoyaltyTransactionStateError(LoyaltyDomainError):
    """The requested status transition is not valid for the transaction's
    current status (e.g. consuming a reservation that isn't RESERVED)."""


class InsufficientLoyaltyPointsError(LoyaltyDomainError):
    """A redeem/reserve was attempted for more points than the account's
    current balance allows (master prompt §66:
    ``InsufficientPointsError``)."""


class LoyaltyTransactionNotFoundError(LoyaltyDomainError):
    """No LoyaltyTransaction with the given id/operation_id exists."""


# ── LOY-7: niveles ────────────────────────────────────────────────────────

class LoyaltyTierNotFoundError(LoyaltyDomainError):
    """No LoyaltyTier with the given id exists."""


class InvalidLoyaltyTierError(LoyaltyDomainError):
    """A tier's configuration is invalid (missing code/name, negative
    minimums, non-Decimal money/multiplier, or a rank that collides with
    another tier in the same program)."""


# ── LOY-8: recompensas ───────────────────────────────────────────────────

class RewardNotFoundError(LoyaltyDomainError):
    """No Reward with the given id exists."""


class RewardNotAvailableError(LoyaltyDomainError):
    """The reward exists but cannot be redeemed right now (inactive, or the
    membership belongs to a different program) — master prompt §66's own
    literal name."""


class InvalidRewardError(LoyaltyDomainError):
    """A reward's configuration is invalid (missing code/name, non-positive
    points_cost, non-Decimal value)."""


class RewardRedemptionNotFoundError(LoyaltyDomainError):
    """No RewardRedemption with the given id exists."""


class InvalidRewardRedemptionStateError(LoyaltyDomainError):
    """The requested transition is not valid for the redemption's current
    status (e.g. confirming one that is already CANCELLED)."""


# ── LOY-9: gamificación ──────────────────────────────────────────────────

class LoyaltyChallengeNotFoundError(LoyaltyDomainError):
    """No LoyaltyChallenge with the given id exists."""


class InvalidLoyaltyChallengeStateError(LoyaltyDomainError):
    """The requested transition is not valid for the challenge's current
    status, or its configuration is invalid (missing code/name, non-
    positive target_value/points_reward)."""


class InvalidChallengeProgressError(LoyaltyDomainError):
    """A progress increment is invalid (negative amount) or the progress
    row is already completed and cannot advance further."""


# ── LOY-10: referidos ────────────────────────────────────────────────────

class ReferralNotFoundError(LoyaltyDomainError):
    """No Referral with the given id exists."""


class InvalidReferralStateError(LoyaltyDomainError):
    """The requested transition is not valid for the referral's current
    status, or its configuration is invalid (missing referrer/referred,
    negative bonus amounts)."""


class ReferralNotQualifiedError(LoyaltyDomainError):
    """A reward was attempted on a referral that has not reached QUALIFIED
    — master prompt §66's own literal name."""


class SelfReferralNotAllowedError(LoyaltyDomainError):
    """The referrer and the referred customer are the same person — real
    antifraude rule (master prompt §17/§29: 'auto-referidos')."""


# ── LOY-11: campañas ─────────────────────────────────────────────────────

class CampaignNotFoundError(LoyaltyDomainError):
    """No Campaign with the given id exists."""


class InvalidCampaignStateError(LoyaltyDomainError):
    """The requested transition is not valid for the campaign's current
    status, or its configuration is invalid (missing code/name)."""


class CampaignBudgetExceededError(LoyaltyDomainError):
    """A spend against the campaign's `budget_limit` would exceed it."""


# ── LOY-14: cumpleaños y retención ───────────────────────────────────────

class InvalidBirthdayBenefitConfigError(LoyaltyDomainError):
    """A birthday benefit configuration is invalid (e.g. `benefit_type`
    requires a reference id that wasn't provided)."""


class BirthdayBenefitConfigNotFoundError(LoyaltyDomainError):
    """No BirthdayBenefitConfig exists for the given program."""


class ConsentRequiredError(LoyaltyDomainError):
    """A marketing/promotional benefit was attempted for a customer without
    the required consent (master prompt §18: 'Debe respetar
    consentimientos', §53)."""


class CampaignNotEligibleForBenefitError(LoyaltyDomainError):
    """A win-back benefit was requested against a campaign that is not
    ACTIVE, not a WIN_BACK/RETENTION type, or has no benefit configured."""


class DuplicateOperationError(LoyaltyDomainError):
    """A ledger operation was attempted with an ``operation_id`` that has
    already been used — idempotency guard (master prompt §12)."""


# ── LOY-26: antifraude ───────────────────────────────────────────────────

class InvalidFraudCaseError(LoyaltyDomainError):
    """A fraud case's configuration is invalid (missing subject/reason)."""


class FraudCaseNotFoundError(LoyaltyDomainError):
    """No FraudCase with the given id exists."""


class InvalidFraudCaseStateError(LoyaltyDomainError):
    """The requested transition is not valid for the fraud case's current
    status."""
