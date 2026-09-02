"""LoyaltyResult — the return type every Fidelidad/Loyalty use case produces.
Mirrors backend/application/sales/result.py's `SaleResult` shape exactly
(this repo's per-context Result convention — no shared base class exists for
it anywhere, confirmed in SALES-6's own research).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.domain.commercial_instruments.exceptions import (
    CouponDefinitionNotFoundError,
    CouponInactiveError,
    VoucherDefinitionNotFoundError,
)
from backend.domain.loyalty.exceptions import (
    BirthdayBenefitConfigNotFoundError,
    CampaignBudgetExceededError,
    CampaignNotEligibleForBenefitError,
    CampaignNotFoundError,
    ConsentRequiredError,
    DuplicateOperationError,
    FraudCaseNotFoundError,
    InsufficientLoyaltyPointsError,
    InvalidFraudCaseError,
    InvalidFraudCaseStateError,
    InvalidLoyaltyAccountStateError,
    InvalidLoyaltyAuditFieldError,
    InvalidLoyaltyMembershipStateError,
    InvalidLoyaltyProgramStateError,
    InvalidLoyaltyTransactionAmountError,
    InvalidLoyaltyTransactionStateError,
    InvalidCampaignStateError,
    InvalidChallengeProgressError,
    InvalidLoyaltyChallengeStateError,
    InvalidRewardError,
    InvalidRewardRedemptionStateError,
    InvalidReferralStateError,
    LoyaltyAccountNotFoundError,
    LoyaltyChallengeNotFoundError,
    LoyaltyAccountSuspendedError,
    LoyaltyConfigurationError,
    LoyaltyDomainError,
    LoyaltyMembershipNotFoundError,
    LoyaltyPermissionDeniedError,
    LoyaltyProgramInactiveError,
    LoyaltyProgramNotFoundError,
    LoyaltySegregationOfDutiesError,
    LoyaltyTransactionNotFoundError,
    ReferralNotFoundError,
    ReferralNotQualifiedError,
    RewardNotAvailableError,
    RewardNotFoundError,
    RewardRedemptionNotFoundError,
    SelfReferralNotAllowedError,
)


@dataclass(frozen=True, slots=True)
class LoyaltyResult:
    success: bool
    message: str = ""
    operation_id: str | None = None
    entity_id: str | None = None
    error_code: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, message: str = "", *, entity_id: str | None = None,
           operation_id: str | None = None, **data: Any) -> "LoyaltyResult":
        return cls(True, message, operation_id, entity_id, None, dict(data))

    @classmethod
    def fail(cls, message: str, error_code: str, *,
             operation_id: str | None = None, **data: Any) -> "LoyaltyResult":
        return cls(False, message, operation_id, None, error_code, dict(data))


_ERROR_CODES: tuple[tuple[type[Exception], str], ...] = (
    (LoyaltyPermissionDeniedError, "PERMISSION_DENIED"),
    (LoyaltyConfigurationError, "CONFIGURATION_ERROR"),
    (LoyaltySegregationOfDutiesError, "SEGREGATION_OF_DUTIES"),
    (InvalidLoyaltyAuditFieldError, "INVALID_AUDIT_FIELD"),
    (LoyaltyProgramNotFoundError, "PROGRAM_NOT_FOUND"),
    (LoyaltyProgramInactiveError, "PROGRAM_INACTIVE"),
    (InvalidLoyaltyProgramStateError, "PROGRAM_INVALID_STATE"),
    (LoyaltyAccountNotFoundError, "ACCOUNT_NOT_FOUND"),
    (LoyaltyAccountSuspendedError, "ACCOUNT_SUSPENDED"),
    (InvalidLoyaltyAccountStateError, "ACCOUNT_INVALID_STATE"),
    (LoyaltyMembershipNotFoundError, "MEMBERSHIP_NOT_FOUND"),
    (InvalidLoyaltyMembershipStateError, "MEMBERSHIP_INVALID_STATE"),
    (InvalidLoyaltyTransactionAmountError, "INVALID_TRANSACTION_AMOUNT"),
    (InvalidLoyaltyTransactionStateError, "TRANSACTION_INVALID_STATE"),
    (LoyaltyTransactionNotFoundError, "TRANSACTION_NOT_FOUND"),
    (InsufficientLoyaltyPointsError, "INSUFFICIENT_POINTS"),
    (DuplicateOperationError, "DUPLICATE_OPERATION"),
    (RewardNotFoundError, "REWARD_NOT_FOUND"),
    (RewardNotAvailableError, "REWARD_NOT_AVAILABLE"),
    (InvalidRewardError, "INVALID_REWARD"),
    (RewardRedemptionNotFoundError, "REWARD_REDEMPTION_NOT_FOUND"),
    (InvalidRewardRedemptionStateError, "REWARD_REDEMPTION_INVALID_STATE"),
    (LoyaltyChallengeNotFoundError, "CHALLENGE_NOT_FOUND"),
    (InvalidLoyaltyChallengeStateError, "CHALLENGE_INVALID_STATE"),
    (InvalidChallengeProgressError, "CHALLENGE_PROGRESS_INVALID"),
    (ReferralNotFoundError, "REFERRAL_NOT_FOUND"),
    (ReferralNotQualifiedError, "REFERRAL_NOT_QUALIFIED"),
    (SelfReferralNotAllowedError, "SELF_REFERRAL_NOT_ALLOWED"),
    (InvalidReferralStateError, "REFERRAL_INVALID_STATE"),
    (CampaignNotFoundError, "CAMPAIGN_NOT_FOUND"),
    (InvalidCampaignStateError, "CAMPAIGN_INVALID_STATE"),
    (CampaignBudgetExceededError, "CAMPAIGN_BUDGET_EXCEEDED"),
    (CampaignNotEligibleForBenefitError, "CAMPAIGN_NOT_ELIGIBLE"),
    (BirthdayBenefitConfigNotFoundError, "BIRTHDAY_CONFIG_NOT_FOUND"),
    (ConsentRequiredError, "CONSENT_REQUIRED"),
    (CouponDefinitionNotFoundError, "COUPON_DEFINITION_NOT_FOUND"),
    (CouponInactiveError, "COUPON_INACTIVE"),
    (VoucherDefinitionNotFoundError, "VOUCHER_DEFINITION_NOT_FOUND"),
    (FraudCaseNotFoundError, "FRAUD_CASE_NOT_FOUND"),
    (InvalidFraudCaseError, "INVALID_FRAUD_CASE"),
    (InvalidFraudCaseStateError, "FRAUD_CASE_INVALID_STATE"),
)


def fail_from_domain_error(exc: LoyaltyDomainError | Exception, *,
                            operation_id: str | None = None) -> LoyaltyResult:
    """Translate any typed Loyalty domain exception (or, since LOY-24's
    birthday-coupon/voucher grant, a Commercial Instruments one reused
    directly from within a Loyalty use case) into a `LoyaltyResult.fail()`
    — one mapping table instead of a bespoke try/except per use case."""
    code = next((code for cls, code in _ERROR_CODES if isinstance(exc, cls)), "VALIDATION")
    return LoyaltyResult.fail(str(exc), code, operation_id=operation_id)
