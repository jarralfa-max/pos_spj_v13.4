"""LOY-17 — Loyalty Card template use cases (master prompt §33-34)."""

from __future__ import annotations

import json
import sqlite3

import pytest

from backend.application.loyalty_cards.authorization import LoyaltyCardsAuthorizationPolicy
from backend.application.loyalty_cards.use_cases.template_use_cases import (
    ActivateLoyaltyCardTemplateVersionUseCase,
    ApproveLoyaltyCardTemplateUseCase,
    ApproveLoyaltyCardTemplateVersionUseCase,
    ArchiveLoyaltyCardTemplateUseCase,
    CreateLoyaltyCardTemplateUseCase,
    CreateLoyaltyCardTemplateVersionUseCase,
)
from backend.infrastructure.db.repositories.loyalty_cards.unit_of_work import (
    LoyaltyCardsUnitOfWork,
)
from backend.infrastructure.db.schema.loyalty_cards_schema import create_loyalty_cards_schema
from backend.shared.ids import new_uuid

_VALID_SCHEMA = json.dumps({
    "canvas": {"width_mm": "85.6", "height_mm": "54", "background_color": "#FFFFFF"},
    "elements": [
        {"type": "TEXT", "x_mm": "5", "y_mm": "5", "width_mm": "40", "height_mm": "10",
         "content": "{{customer_name}}"},
    ],
})


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    create_loyalty_cards_schema(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture
def auth():
    return LoyaltyCardsAuthorizationPolicy.permissive_for_tests()


def _approved_template(conn, auth):
    create = CreateLoyaltyCardTemplateUseCase(auth).execute(
        conn, code="T1", name="Plantilla clásica", actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid())
    ApproveLoyaltyCardTemplateUseCase(auth).execute(
        conn, template_id=create.entity_id, actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid())
    return create.entity_id


class TestTemplateLifecycle:
    def test_create_starts_pending_approval(self, conn, auth):
        create = CreateLoyaltyCardTemplateUseCase(auth).execute(
            conn, code="T1", name="Plantilla", actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert create.success

    def test_approve(self, conn, auth):
        template_id = _approved_template(conn, auth)
        with LoyaltyCardsUnitOfWork(conn) as uow:
            template = uow.templates.get(template_id)
            assert template.status.value == "APPROVED"

    def test_archive(self, conn, auth):
        template_id = _approved_template(conn, auth)
        result = ArchiveLoyaltyCardTemplateUseCase(auth).execute(
            conn, template_id=template_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success

    def test_template_not_found(self, conn, auth):
        result = ApproveLoyaltyCardTemplateUseCase(auth).execute(
            conn, template_id=new_uuid(), actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "TEMPLATE_NOT_FOUND"


class TestTemplateVersionFlow:
    def test_create_version(self, conn, auth):
        template_id = _approved_template(conn, auth)
        result = CreateLoyaltyCardTemplateVersionUseCase(auth).execute(
            conn, template_id=template_id, design_schema_json=_VALID_SCHEMA,
            actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["version_number"] == 1

    def test_second_version_increments_number(self, conn, auth):
        template_id = _approved_template(conn, auth)
        CreateLoyaltyCardTemplateVersionUseCase(auth).execute(
            conn, template_id=template_id, design_schema_json=_VALID_SCHEMA, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        result = CreateLoyaltyCardTemplateVersionUseCase(auth).execute(
            conn, template_id=template_id, design_schema_json=_VALID_SCHEMA, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.data["version_number"] == 2

    def test_activate_version_activates_template(self, conn, auth):
        template_id = _approved_template(conn, auth)
        version = CreateLoyaltyCardTemplateVersionUseCase(auth).execute(
            conn, template_id=template_id, design_schema_json=_VALID_SCHEMA, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        ApproveLoyaltyCardTemplateVersionUseCase(auth).execute(
            conn, version_id=version.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        result = ActivateLoyaltyCardTemplateVersionUseCase(auth).execute(
            conn, version_id=version.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        with LoyaltyCardsUnitOfWork(conn) as uow:
            template = uow.templates.get(template_id)
            assert template.status.value == "ACTIVE"
            assert template.active_version_id == version.entity_id
            assert template.is_available_for_issuance()

    def test_activating_new_version_archives_previous_active(self, conn, auth):
        template_id = _approved_template(conn, auth)
        v1 = CreateLoyaltyCardTemplateVersionUseCase(auth).execute(
            conn, template_id=template_id, design_schema_json=_VALID_SCHEMA, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        ApproveLoyaltyCardTemplateVersionUseCase(auth).execute(
            conn, version_id=v1.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        ActivateLoyaltyCardTemplateVersionUseCase(auth).execute(
            conn, version_id=v1.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())

        v2 = CreateLoyaltyCardTemplateVersionUseCase(auth).execute(
            conn, template_id=template_id, design_schema_json=_VALID_SCHEMA, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        ApproveLoyaltyCardTemplateVersionUseCase(auth).execute(
            conn, version_id=v2.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        result = ActivateLoyaltyCardTemplateVersionUseCase(auth).execute(
            conn, version_id=v2.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success

        with LoyaltyCardsUnitOfWork(conn) as uow:
            old_version = uow.template_versions.get(v1.entity_id)
            new_version = uow.template_versions.get(v2.entity_id)
            template = uow.templates.get(template_id)
            assert old_version.status.value == "ARCHIVED"
            assert new_version.status.value == "ACTIVE"
            assert template.active_version_id == v2.entity_id

    def test_cannot_activate_unapproved_version(self, conn, auth):
        template_id = _approved_template(conn, auth)
        version = CreateLoyaltyCardTemplateVersionUseCase(auth).execute(
            conn, template_id=template_id, design_schema_json=_VALID_SCHEMA, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        result = ActivateLoyaltyCardTemplateVersionUseCase(auth).execute(
            conn, version_id=version.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "TEMPLATE_VERSION_INVALID_STATE"
