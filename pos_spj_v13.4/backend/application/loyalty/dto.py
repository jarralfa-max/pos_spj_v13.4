"""Read-side DTOs for the Fidelidad/Loyalty application layer — flat, frozen
projections a caller (UI/API) can use without touching domain entities
directly. Mirrors backend/application/sales/dto.py's style.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.loyalty.entities.loyalty_account import LoyaltyAccount
from backend.domain.loyalty.entities.loyalty_membership import LoyaltyMembership
from backend.domain.loyalty.entities.loyalty_program import LoyaltyProgram
from backend.domain.loyalty.entities.loyalty_tier import LoyaltyTier
from backend.domain.loyalty.entities.loyalty_transaction import LoyaltyTransaction
from backend.domain.loyalty.entities.challenge_progress import ChallengeProgress
from backend.domain.loyalty.entities.loyalty_challenge import LoyaltyChallenge
from backend.domain.loyalty.entities.campaign import Campaign
from backend.domain.loyalty.entities.referral import Referral
from backend.domain.loyalty.entities.reward import Reward
from backend.domain.loyalty.entities.reward_redemption import RewardRedemption


@dataclass(frozen=True, slots=True)
class LoyaltyProgramDTO:
    id: str
    code: str
    name: str
    currency_name: str
    description: str
    status: str
    enrollment_mode: str
    earning_enabled: bool
    redemption_enabled: bool
    tiering_enabled: bool
    expiration_enabled: bool
    approved_by_user_id: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_entity(cls, program: LoyaltyProgram) -> "LoyaltyProgramDTO":
        return cls(
            id=program.id, code=program.code, name=program.name,
            currency_name=program.currency_name, description=program.description,
            status=program.status.value, enrollment_mode=program.enrollment_mode,
            earning_enabled=program.earning_enabled,
            redemption_enabled=program.redemption_enabled,
            tiering_enabled=program.tiering_enabled,
            expiration_enabled=program.expiration_enabled,
            approved_by_user_id=program.approved_by_user_id,
            created_at=program.created_at, updated_at=program.updated_at,
        )


@dataclass(frozen=True, slots=True)
class LoyaltyAccountDTO:
    id: str
    customer_id: str
    status: str
    created_at: str

    @classmethod
    def from_entity(cls, account: LoyaltyAccount) -> "LoyaltyAccountDTO":
        return cls(id=account.id, customer_id=account.customer_id,
                    status=account.status.value, created_at=account.created_at)


@dataclass(frozen=True, slots=True)
class LoyaltyMembershipDTO:
    id: str
    loyalty_account_id: str
    program_id: str
    current_tier_id: str | None
    status: str
    enrolled_at: str

    @classmethod
    def from_entity(cls, membership: LoyaltyMembership) -> "LoyaltyMembershipDTO":
        return cls(
            id=membership.id, loyalty_account_id=membership.loyalty_account_id,
            program_id=membership.program_id, current_tier_id=membership.current_tier_id,
            status=membership.status.value, enrolled_at=membership.enrolled_at,
        )


@dataclass(frozen=True, slots=True)
class LoyaltyTransactionDTO:
    id: str
    loyalty_account_id: str
    transaction_type: str
    points_amount: Decimal
    status: str
    operation_id: str
    reason_code: str | None
    created_at: str

    @classmethod
    def from_entity(cls, transaction: LoyaltyTransaction) -> "LoyaltyTransactionDTO":
        return cls(
            id=transaction.id, loyalty_account_id=transaction.loyalty_account_id,
            transaction_type=transaction.transaction_type.value,
            points_amount=transaction.points_amount, status=transaction.status.value,
            operation_id=transaction.operation_id, reason_code=transaction.reason_code,
            created_at=transaction.created_at,
        )


@dataclass(frozen=True, slots=True)
class LoyaltyTierDTO:
    id: str
    program_id: str
    code: str
    name: str
    rank: int
    minimum_points: Decimal
    minimum_spend: Decimal
    minimum_visits: int
    benefit_multiplier: Decimal
    active: bool

    @classmethod
    def from_entity(cls, tier: LoyaltyTier) -> "LoyaltyTierDTO":
        return cls(
            id=tier.id, program_id=tier.program_id, code=tier.code, name=tier.name,
            rank=tier.rank, minimum_points=tier.minimum_points,
            minimum_spend=tier.minimum_spend, minimum_visits=tier.minimum_visits,
            benefit_multiplier=tier.benefit_multiplier, active=tier.active,
        )


@dataclass(frozen=True, slots=True)
class RewardDTO:
    id: str
    program_id: str
    code: str
    name: str
    reward_type: str
    points_cost: Decimal
    value: Decimal
    active: bool

    @classmethod
    def from_entity(cls, reward: Reward) -> "RewardDTO":
        return cls(
            id=reward.id, program_id=reward.program_id, code=reward.code, name=reward.name,
            reward_type=reward.reward_type.value, points_cost=reward.points_cost,
            value=reward.value, active=reward.active,
        )


@dataclass(frozen=True, slots=True)
class RewardRedemptionDTO:
    id: str
    reward_id: str
    membership_id: str
    points_transaction_id: str
    status: str
    requested_at: str

    @classmethod
    def from_entity(cls, redemption: RewardRedemption) -> "RewardRedemptionDTO":
        return cls(
            id=redemption.id, reward_id=redemption.reward_id,
            membership_id=redemption.membership_id,
            points_transaction_id=redemption.points_transaction_id,
            status=redemption.status.value, requested_at=redemption.requested_at,
        )


@dataclass(frozen=True, slots=True)
class LoyaltyChallengeDTO:
    id: str
    program_id: str
    code: str
    name: str
    mode: str
    criteria_type: str
    target_value: Decimal
    points_reward: Decimal
    status: str

    @classmethod
    def from_entity(cls, challenge: LoyaltyChallenge) -> "LoyaltyChallengeDTO":
        return cls(
            id=challenge.id, program_id=challenge.program_id, code=challenge.code,
            name=challenge.name, mode=challenge.mode.value,
            criteria_type=challenge.criteria_type.value,
            target_value=challenge.target_value, points_reward=challenge.points_reward,
            status=challenge.status.value,
        )


@dataclass(frozen=True, slots=True)
class ChallengeProgressDTO:
    id: str
    challenge_id: str
    membership_id: str
    current_value: Decimal
    completed: bool
    points_awarded: Decimal

    @classmethod
    def from_entity(cls, progress: ChallengeProgress) -> "ChallengeProgressDTO":
        return cls(
            id=progress.id, challenge_id=progress.challenge_id,
            membership_id=progress.membership_id, current_value=progress.current_value,
            completed=progress.completed, points_awarded=progress.points_awarded,
        )


@dataclass(frozen=True, slots=True)
class ReferralDTO:
    id: str
    program_id: str
    referrer_membership_id: str
    referred_customer_id: str
    referrer_bonus_points: Decimal
    status: str
    registered_at: str

    @classmethod
    def from_entity(cls, referral: Referral) -> "ReferralDTO":
        return cls(
            id=referral.id, program_id=referral.program_id,
            referrer_membership_id=referral.referrer_membership_id,
            referred_customer_id=referral.referred_customer_id,
            referrer_bonus_points=referral.referrer_bonus_points,
            status=referral.status.value, registered_at=referral.registered_at,
        )


@dataclass(frozen=True, slots=True)
class CampaignDTO:
    id: str
    program_id: str
    code: str
    name: str
    campaign_type: str
    status: str
    created_by_user_id: str
    approved_by_user_id: str | None

    @classmethod
    def from_entity(cls, campaign: Campaign) -> "CampaignDTO":
        return cls(
            id=campaign.id, program_id=campaign.program_id, code=campaign.code,
            name=campaign.name, campaign_type=campaign.campaign_type.value,
            status=campaign.status.value, created_by_user_id=campaign.created_by_user_id,
            approved_by_user_id=campaign.approved_by_user_id,
        )


@dataclass(frozen=True, slots=True)
class LoyaltyAccountSummaryDTO:
    """The one cross-context read most other bounded contexts actually need
    (master prompt §21/§23: Sales' EvaluateCustomerBenefitsQuery,
    CRM's LoyaltyCustomerSummaryQuery — neither exists as a caller yet, but
    this is the shape they'll consume) — balance already reconstructed via
    LoyaltyBalancePolicy, never raw ledger rows."""

    loyalty_account_id: str
    customer_id: str
    account_status: str
    balance: Decimal
    reserved_amount: Decimal
    memberships: tuple[LoyaltyMembershipDTO, ...]
