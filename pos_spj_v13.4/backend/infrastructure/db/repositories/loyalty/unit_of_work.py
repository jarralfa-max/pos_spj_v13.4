"""LoyaltyUnitOfWork — one transaction boundary for the Fidelidad/Loyalty
context. Mirrors backend/infrastructure/db/repositories/sales/unit_of_work.py's
`SalesUnitOfWork` exactly (same `owns_transaction` flag, same
`__enter__`/`__exit__` shape) — a real accrual/redemption will often need to
compose Loyalty + Sales + Finance writes inside one outer SAVEPOINT, the same
scenario Inventory/Sales's own docstrings already name.

Repositories never commit; this UoW commits on clean exit and rolls back on
any exception, guaranteeing atomicity across a program/account/membership
write and any ledger transaction + outbox event enqueued alongside it.
"""

from __future__ import annotations

from typing import Any

from backend.infrastructure.db.repositories.loyalty.account_repository import (
    LoyaltyAccountRepository,
)
from backend.infrastructure.db.repositories.loyalty.membership_repository import (
    LoyaltyMembershipRepository,
)
from backend.infrastructure.db.repositories.loyalty.outbox_repository import (
    LoyaltyOutboxRepository,
)
from backend.infrastructure.db.repositories.loyalty.program_repository import (
    LoyaltyProgramRepository,
)
from backend.infrastructure.db.repositories.loyalty.fraud_case_repository import (
    FraudCaseRepository,
)
from backend.infrastructure.db.repositories.loyalty.birthday_config_repository import (
    BirthdayBenefitConfigRepository,
)
from backend.infrastructure.db.repositories.loyalty.campaign_repository import (
    CampaignRepository,
)
from backend.infrastructure.db.repositories.loyalty.gamification_repository import (
    ChallengeProgressRepository,
    LoyaltyBadgeRepository,
    LoyaltyChallengeRepository,
    LoyaltyStreakRepository,
)
from backend.infrastructure.db.repositories.loyalty.referral_repository import (
    ReferralRepository,
)
from backend.infrastructure.db.repositories.loyalty.reward_repository import (
    RewardRedemptionRepository,
    RewardRepository,
)
from backend.infrastructure.db.repositories.loyalty.tier_repository import (
    LoyaltyTierHistoryRepository,
    LoyaltyTierRepository,
)
from backend.infrastructure.db.repositories.loyalty.transaction_repository import (
    LoyaltyTransactionRepository,
)


class LoyaltyUnitOfWork:
    def __init__(self, connection: Any, *, owns_transaction: bool = True) -> None:
        self.connection = connection
        self._owns_transaction = owns_transaction
        self.programs = LoyaltyProgramRepository(connection)
        self.accounts = LoyaltyAccountRepository(connection)
        self.memberships = LoyaltyMembershipRepository(connection)
        self.transactions = LoyaltyTransactionRepository(connection)
        self.tiers = LoyaltyTierRepository(connection)
        self.tier_history = LoyaltyTierHistoryRepository(connection)
        self.rewards = RewardRepository(connection)
        self.reward_redemptions = RewardRedemptionRepository(connection)
        self.challenges = LoyaltyChallengeRepository(connection)
        self.challenge_progress = ChallengeProgressRepository(connection)
        self.streaks = LoyaltyStreakRepository(connection)
        self.badges = LoyaltyBadgeRepository(connection)
        self.referrals = ReferralRepository(connection)
        self.campaigns = CampaignRepository(connection)
        self.birthday_configs = BirthdayBenefitConfigRepository(connection)
        self.fraud_cases = FraudCaseRepository(connection)
        self.outbox = LoyaltyOutboxRepository(connection)
        self._completed = False

    def __enter__(self) -> "LoyaltyUnitOfWork":
        self._completed = False
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is not None:
            self.rollback()
        elif not self._completed:
            self.commit()
        return False

    def commit(self) -> None:
        if self._owns_transaction:
            self.connection.commit()
        self._completed = True

    def rollback(self) -> None:
        if self._owns_transaction:
            rollback = getattr(self.connection, "rollback", None)
            if rollback is not None:
                rollback()
        self._completed = True
