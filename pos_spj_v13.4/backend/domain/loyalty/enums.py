"""Canonical enums for the Fidelidad/Loyalty domain base (LOY-2, master
prompt §9-§11)."""

from __future__ import annotations

from enum import Enum


class ProgramStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"
    ARCHIVED = "ARCHIVED"


class AccountStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"


class MembershipStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    BLOCKED = "BLOCKED"
    CLOSED = "CLOSED"


class TransactionType(str, Enum):
    EARN = "EARN"
    BONUS = "BONUS"
    REDEEM = "REDEEM"
    RESERVE = "RESERVE"
    RELEASE = "RELEASE"
    EXPIRE = "EXPIRE"
    ADJUSTMENT = "ADJUSTMENT"
    REVERSAL = "REVERSAL"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"


class TransactionStatus(str, Enum):
    PENDING = "PENDING"
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    CONSUMED = "CONSUMED"
    EXPIRED = "EXPIRED"
    REVERSED = "REVERSED"
    CANCELLED = "CANCELLED"


class TierEvaluationMethod(str, Enum):
    """§14: how a tier's evaluation window is computed."""
    ROLLING_PERIOD = "ROLLING_PERIOD"
    CALENDAR_YEAR = "CALENDAR_YEAR"
    LIFETIME = "LIFETIME"
    FIXED_PERIOD = "FIXED_PERIOD"


class RewardType(str, Enum):
    """§15."""
    PRODUCT = "PRODUCT"
    DISCOUNT = "DISCOUNT"
    FIXED_AMOUNT = "FIXED_AMOUNT"
    PERCENTAGE = "PERCENTAGE"
    FREE_DELIVERY = "FREE_DELIVERY"
    COUPON = "COUPON"
    VOUCHER = "VOUCHER"
    EXPERIENCE = "EXPERIENCE"
    OTHER = "OTHER"


class ChallengeMode(str, Enum):
    """§16 names LoyaltyChallenge/LoyaltyMission/LoyaltyMilestone as
    separate classes but gives no distinguishing field list for any of
    them — this discriminator collapses the three into one entity
    (`LoyaltyChallenge`) rather than three near-identical duplicates (this
    repo's own "una sola ruta canónica" principle). LoyaltyStreak/
    LoyaltyBadge keep their own distinct entities since they genuinely have
    a different shape (running counters / award records)."""
    CHALLENGE = "CHALLENGE"
    MISSION = "MISSION"
    MILESTONE = "MILESTONE"


class ChallengeCriteriaType(str, Enum):
    """§16."""
    PURCHASE_COUNT = "PURCHASE_COUNT"
    SPEND_AMOUNT = "SPEND_AMOUNT"
    PRODUCT_CATEGORY = "PRODUCT_CATEGORY"
    PRODUCT_PURCHASE = "PRODUCT_PURCHASE"
    BRANCH_VISIT = "BRANCH_VISIT"
    REFERRAL = "REFERRAL"
    BIRTHDAY = "BIRTHDAY"
    CONSECUTIVE_WEEKS = "CONSECUTIVE_WEEKS"
    MULTI_CATEGORY = "MULTI_CATEGORY"
    CUSTOM_RULE = "CUSTOM_RULE"


class ChallengeStatus(str, Enum):
    """§16."""
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class CampaignType(str, Enum):
    """§19."""
    ACQUISITION = "ACQUISITION"
    RETENTION = "RETENTION"
    WIN_BACK = "WIN_BACK"
    BIRTHDAY = "BIRTHDAY"
    REFERRAL = "REFERRAL"
    SEASONAL = "SEASONAL"
    PRODUCT_PUSH = "PRODUCT_PUSH"
    BRANCH_SPECIFIC = "BRANCH_SPECIFIC"
    LOYALTY_TIER = "LOYALTY_TIER"
    CLEARANCE = "CLEARANCE"


class CampaignStatus(str, Enum):
    """§19."""
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    SCHEDULED = "SCHEDULED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class BirthdayBenefitType(str, Enum):
    """§18."""
    POINTS = "POINTS"
    COUPON = "COUPON"
    VOUCHER = "VOUCHER"
    REWARD = "REWARD"
    NONE = "NONE"


class ReferralStatus(str, Enum):
    """§17."""
    REGISTERED = "REGISTERED"
    QUALIFIED = "QUALIFIED"
    REWARDED = "REWARDED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    FRAUD_SUSPECTED = "FRAUD_SUSPECTED"


class RewardRedemptionStatus(str, Enum):
    """§15 flow: Validar → Reservar puntos → ... → Confirmar canje; en
    cancelación: Liberar reserva. Mirrors the RESERVE/CONSUMED/CANCELLED
    subset of `TransactionStatus` (LOY-2) that applies to a redemption
    record specifically."""
    RESERVED = "RESERVED"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class FraudCaseSubjectType(str, Enum):
    """§29 — what kind of record a fraud case is flagging. Not limited to
    Loyalty's own entities: a case can point at a Commercial Instruments
    coupon/voucher or a Sweepstakes entry/ticket, both reached via an
    unchecked opaque id (same bounded-context-isolation discipline as
    every cross-context reference in this pipeline)."""
    REFERRAL = "REFERRAL"
    TRANSACTION = "TRANSACTION"
    MEMBERSHIP = "MEMBERSHIP"
    COUPON = "COUPON"
    VOUCHER = "VOUCHER"
    SWEEPSTAKES_ENTRY = "SWEEPSTAKES_ENTRY"


class FraudCaseStatus(str, Enum):
    """§29."""
    OPEN = "OPEN"
    UNDER_REVIEW = "UNDER_REVIEW"
    CONFIRMED = "CONFIRMED"
    DISMISSED = "DISMISSED"


class LoyaltyRuleType(str, Enum):
    """§13 — tipos de regla de acumulación. Los marcados en
    `SALE_EVALUATED_RULE_TYPES` los ejecuta el POS al cobrar; los demás los
    otorga su propio flujo (Referidos, Retos)."""
    POINTS_PER_AMOUNT = "POINTS_PER_AMOUNT"
    POINTS_PER_UNIT = "POINTS_PER_UNIT"
    FIXED_BONUS = "FIXED_BONUS"
    CATEGORY_MULTIPLIER = "CATEGORY_MULTIPLIER"
    PRODUCT_MULTIPLIER = "PRODUCT_MULTIPLIER"
    BRANCH_MULTIPLIER = "BRANCH_MULTIPLIER"
    CHANNEL_MULTIPLIER = "CHANNEL_MULTIPLIER"
    PAYMENT_METHOD_MULTIPLIER = "PAYMENT_METHOD_MULTIPLIER"
    BIRTHDAY_BONUS = "BIRTHDAY_BONUS"
    REFERRAL_BONUS = "REFERRAL_BONUS"
    FIRST_PURCHASE_BONUS = "FIRST_PURCHASE_BONUS"
    VISIT_FREQUENCY_BONUS = "VISIT_FREQUENCY_BONUS"
    CHALLENGE_REWARD = "CHALLENGE_REWARD"
    CAMPAIGN_BONUS = "CAMPAIGN_BONUS"


#: Los que se evalúan con los datos de una compra.
SALE_EVALUATED_RULE_TYPES = frozenset({
    LoyaltyRuleType.POINTS_PER_AMOUNT, LoyaltyRuleType.POINTS_PER_UNIT,
    LoyaltyRuleType.FIXED_BONUS, LoyaltyRuleType.CATEGORY_MULTIPLIER,
    LoyaltyRuleType.PRODUCT_MULTIPLIER, LoyaltyRuleType.BRANCH_MULTIPLIER,
    LoyaltyRuleType.CHANNEL_MULTIPLIER, LoyaltyRuleType.PAYMENT_METHOD_MULTIPLIER,
    LoyaltyRuleType.FIRST_PURCHASE_BONUS, LoyaltyRuleType.VISIT_FREQUENCY_BONUS,
    LoyaltyRuleType.CAMPAIGN_BONUS,
    # Desde 2026-10-03 el maestro de clientes guarda el cumpleaños (con
    # consentimiento): el bono de cumpleaños se evalúa al cobrar.
    LoyaltyRuleType.BIRTHDAY_BONUS,
})


class LoyaltyRuleStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class StackingCombination(str, Enum):
    """§24 — combinaciones de beneficios en una misma venta."""
    POINTS_COUPON = "POINTS_COUPON"
    POINTS_VOUCHER = "POINTS_VOUCHER"
    COUPON_VOUCHER = "COUPON_VOUCHER"
    COUPON_COUPON = "COUPON_COUPON"
    PROMOTION_COUPON = "PROMOTION_COUPON"
    EMPLOYEE_DISCOUNT_COUPON = "EMPLOYEE_DISCOUNT_COUPON"
    GIFT_CARD_POINTS = "GIFT_CARD_POINTS"
    STORE_CREDIT_COUPON = "STORE_CREDIT_COUPON"


class StackingOption(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    ALLOW_WITH_LIMIT = "ALLOW_WITH_LIMIT"
    EXCLUSIVE = "EXCLUSIVE"
    BEST_BENEFIT_ONLY = "BEST_BENEFIT_ONLY"
    PRIORITY_ORDER = "PRIORITY_ORDER"
