"""LOY-11 — Campaign repository round-trip + use cases (full lifecycle)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.application.loyalty.use_cases.campaign_use_cases import (
    ActivateCampaignUseCase,
    ApproveCampaignUseCase,
    CancelCampaignUseCase,
    CompleteCampaignUseCase,
    CreateCampaignUseCase,
    PauseCampaignUseCase,
    ScheduleCampaignUseCase,
)
from backend.application.loyalty.use_cases.program_use_cases import CreateLoyaltyProgramUseCase
from backend.domain.loyalty.enums import CampaignType
from backend.infrastructure.db.repositories.loyalty.campaign_repository import (
    CampaignRepository,
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


def _program_id(conn, auth) -> str:
    create = CreateLoyaltyProgramUseCase(auth).execute(
        conn, code="PTS", name="Puntos SPJ", currency_name="Estrellas",
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    return create.entity_id


class TestCreateCampaign:
    def test_creates_and_submits_for_approval(self, conn, auth):
        program_id = _program_id(conn, auth)
        result = CreateCampaignUseCase(auth).execute(
            conn, program_id=program_id, code="SUMMER26", name="Verano 2026",
            campaign_type=CampaignType.SEASONAL, actor_user_id=new_uuid(),
            operation_id=new_uuid(), budget_limit=Decimal("5000"))
        assert result.success
        assert result.data["campaign"].status == "PENDING_APPROVAL"

    def test_program_not_found(self, conn, auth):
        result = CreateCampaignUseCase(auth).execute(
            conn, program_id=new_uuid(), code="X", name="X",
            campaign_type=CampaignType.SEASONAL, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "PROGRAM_NOT_FOUND"


class TestCampaignLifecycle:
    def test_full_flow_with_distinct_users(self, conn, auth):
        program_id = _program_id(conn, auth)
        creator = new_uuid()
        create = CreateCampaignUseCase(auth).execute(
            conn, program_id=program_id, code="SUMMER26", name="Verano 2026",
            campaign_type=CampaignType.SEASONAL, actor_user_id=creator,
            operation_id=new_uuid())
        campaign_id = create.entity_id

        approver = new_uuid()
        approve = ApproveCampaignUseCase(auth).execute(
            conn, campaign_id=campaign_id, actor_user_id=approver, operation_id=new_uuid())
        assert approve.success

        ScheduleCampaignUseCase(auth).execute(
            conn, campaign_id=campaign_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        activate = ActivateCampaignUseCase(auth).execute(
            conn, campaign_id=campaign_id, actor_user_id=approver, operation_id=new_uuid())
        assert activate.success
        assert activate.data["campaign"].status == "ACTIVE"

        PauseCampaignUseCase(auth).execute(
            conn, campaign_id=campaign_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        ActivateCampaignUseCase(auth).execute(
            conn, campaign_id=campaign_id, actor_user_id=approver, operation_id=new_uuid())
        complete = CompleteCampaignUseCase(auth).execute(
            conn, campaign_id=campaign_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert complete.data["campaign"].status == "COMPLETED"

        repo = CampaignRepository(conn)
        assert repo.get(campaign_id).status.value == "COMPLETED"

    def test_creator_cannot_approve_own_campaign(self, conn, auth):
        program_id = _program_id(conn, auth)
        creator = new_uuid()
        create = CreateCampaignUseCase(auth).execute(
            conn, program_id=program_id, code="SUMMER26", name="Verano 2026",
            campaign_type=CampaignType.SEASONAL, actor_user_id=creator,
            operation_id=new_uuid())
        result = ApproveCampaignUseCase(auth).execute(
            conn, campaign_id=create.entity_id, actor_user_id=creator,
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "SEGREGATION_OF_DUTIES"

    def test_cancel_requires_reason(self, conn, auth):
        program_id = _program_id(conn, auth)
        create = CreateCampaignUseCase(auth).execute(
            conn, program_id=program_id, code="SUMMER26", name="Verano 2026",
            campaign_type=CampaignType.SEASONAL, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        result = CancelCampaignUseCase(auth).execute(
            conn, campaign_id=create.entity_id, reason="", actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "CAMPAIGN_INVALID_STATE"

    def test_campaign_not_found(self, conn, auth):
        result = ApproveCampaignUseCase(auth).execute(
            conn, campaign_id=new_uuid(), actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "CAMPAIGN_NOT_FOUND"
