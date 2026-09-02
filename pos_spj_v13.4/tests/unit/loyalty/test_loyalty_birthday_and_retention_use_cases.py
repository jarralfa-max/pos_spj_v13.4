"""LOY-14 — Birthday benefit + retention/win-back use cases."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.application.loyalty.use_cases.birthday_use_cases import (
    ConfigureBirthdayBenefitUseCase,
    GrantBirthdayBenefitUseCase,
)
from backend.application.loyalty.use_cases.campaign_use_cases import (
    ActivateCampaignUseCase,
    ApproveCampaignUseCase,
    CreateCampaignUseCase,
)
from backend.application.loyalty.use_cases.membership_use_cases import (
    EnrollLoyaltyMembershipUseCase,
)
from backend.application.loyalty.use_cases.program_use_cases import (
    ActivateLoyaltyProgramUseCase,
    ApproveLoyaltyProgramUseCase,
    CreateLoyaltyProgramUseCase,
)
from backend.application.loyalty.use_cases.retention_use_cases import (
    TriggerCampaignBenefitUseCase,
)
from backend.domain.loyalty.enums import BirthdayBenefitType, CampaignType
from backend.domain.loyalty.policies.balance_policy import LoyaltyBalancePolicy
from backend.infrastructure.db.repositories.loyalty.transaction_repository import (
    LoyaltyTransactionRepository,
)
from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    create_loyalty_schema(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture
def auth():
    return LoyaltyAuthorizationPolicy.permissive_for_tests()


def _balance(conn, account_id) -> Decimal:
    ledger = LoyaltyTransactionRepository(conn).list_for_account(account_id)
    return LoyaltyBalancePolicy.balance(ledger)


def _active_program_and_membership(conn, auth):
    create = CreateLoyaltyProgramUseCase(auth).execute(
        conn, code="PTS", name="Puntos SPJ", currency_name="Estrellas",
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    ApproveLoyaltyProgramUseCase(auth).execute(
        conn, program_id=create.entity_id, actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid())
    ActivateLoyaltyProgramUseCase(auth).execute(
        conn, program_id=create.entity_id, actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid())
    program_id = create.entity_id
    enroll = EnrollLoyaltyMembershipUseCase(auth).execute(
        conn, customer_id=new_uuid(), program_id=program_id,
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    return program_id, enroll.entity_id, enroll.data["membership"].loyalty_account_id


class TestConfigureBirthdayBenefit:
    def test_configures_points_benefit(self, conn, auth):
        program_id, _, _ = _active_program_and_membership(conn, auth)
        result = ConfigureBirthdayBenefitUseCase(auth).execute(
            conn, program_id=program_id, actor_user_id=new_uuid(), operation_id=new_uuid(),
            benefit_type=BirthdayBenefitType.POINTS, points_amount=Decimal("100"))
        assert result.success

    def test_program_not_found(self, conn, auth):
        result = ConfigureBirthdayBenefitUseCase(auth).execute(
            conn, program_id=new_uuid(), actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success


class TestGrantBirthdayBenefit:
    def test_grants_points_with_consent(self, conn, auth):
        program_id, _, account_id = _active_program_and_membership(conn, auth)
        ConfigureBirthdayBenefitUseCase(auth).execute(
            conn, program_id=program_id, actor_user_id=new_uuid(), operation_id=new_uuid(),
            benefit_type=BirthdayBenefitType.POINTS, points_amount=Decimal("100"))

        result = GrantBirthdayBenefitUseCase(auth).execute(
            conn, program_id=program_id, loyalty_account_id=account_id,
            has_marketing_consent=True, actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["granted"] is True
        assert _balance(conn, account_id) == Decimal("100")

    def test_denies_without_consent(self, conn, auth):
        program_id, _, account_id = _active_program_and_membership(conn, auth)
        ConfigureBirthdayBenefitUseCase(auth).execute(
            conn, program_id=program_id, actor_user_id=new_uuid(), operation_id=new_uuid(),
            benefit_type=BirthdayBenefitType.POINTS, points_amount=Decimal("100"))

        result = GrantBirthdayBenefitUseCase(auth).execute(
            conn, program_id=program_id, loyalty_account_id=account_id,
            has_marketing_consent=False, actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "CONSENT_REQUIRED"
        assert _balance(conn, account_id) == Decimal("0")

    def test_no_config_configured(self, conn, auth):
        program_id, _, account_id = _active_program_and_membership(conn, auth)
        result = GrantBirthdayBenefitUseCase(auth).execute(
            conn, program_id=program_id, loyalty_account_id=account_id,
            has_marketing_consent=True, actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "BIRTHDAY_CONFIG_NOT_FOUND"

    def test_disabled_config_grants_nothing_without_error(self, conn, auth):
        program_id, _, account_id = _active_program_and_membership(conn, auth)
        ConfigureBirthdayBenefitUseCase(auth).execute(
            conn, program_id=program_id, actor_user_id=new_uuid(), operation_id=new_uuid(),
            enabled=False, benefit_type=BirthdayBenefitType.POINTS,
            points_amount=Decimal("100"))
        result = GrantBirthdayBenefitUseCase(auth).execute(
            conn, program_id=program_id, loyalty_account_id=account_id,
            has_marketing_consent=True, actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["granted"] is False


class TestTriggerCampaignBenefit:
    def test_grants_points_from_active_winback_campaign(self, conn, auth):
        program_id, membership_id, account_id = _active_program_and_membership(conn, auth)
        creator = new_uuid()
        create = CreateCampaignUseCase(auth).execute(
            conn, program_id=program_id, code="WINBACK1", name="Vuelve con nosotros",
            campaign_type=CampaignType.WIN_BACK, actor_user_id=creator,
            operation_id=new_uuid(), benefit_type="POINTS", benefit_reference_id="150")
        ApproveCampaignUseCase(auth).execute(
            conn, campaign_id=create.entity_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        from backend.application.loyalty.use_cases.campaign_use_cases import (
            ScheduleCampaignUseCase,
        )
        ScheduleCampaignUseCase(auth).execute(
            conn, campaign_id=create.entity_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        ActivateCampaignUseCase(auth).execute(
            conn, campaign_id=create.entity_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())

        result = TriggerCampaignBenefitUseCase(auth).execute(
            conn, campaign_id=create.entity_id, membership_id=membership_id,
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert _balance(conn, account_id) == Decimal("150")

    def test_rejects_inactive_campaign(self, conn, auth):
        program_id, membership_id, _ = _active_program_and_membership(conn, auth)
        create = CreateCampaignUseCase(auth).execute(
            conn, program_id=program_id, code="WINBACK1", name="Vuelve con nosotros",
            campaign_type=CampaignType.WIN_BACK, actor_user_id=new_uuid(),
            operation_id=new_uuid(), benefit_type="POINTS", benefit_reference_id="150")
        result = TriggerCampaignBenefitUseCase(auth).execute(
            conn, campaign_id=create.entity_id, membership_id=membership_id,
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "CAMPAIGN_NOT_ELIGIBLE"

    def test_campaign_not_found(self, conn, auth):
        result = TriggerCampaignBenefitUseCase(auth).execute(
            conn, campaign_id=new_uuid(), membership_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "CAMPAIGN_NOT_FOUND"
