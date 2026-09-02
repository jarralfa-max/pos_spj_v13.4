"""LOY-21 — Loyalty Card batch use cases (master prompt §43-44)."""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal

import pytest

from backend.application.loyalty_cards.authorization import LoyaltyCardsAuthorizationPolicy
from backend.application.loyalty_cards.use_cases.batch_use_cases import (
    ApproveLoyaltyCardBatchUseCase,
    CancelLoyaltyCardBatchUseCase,
    CreateLoyaltyCardBatchUseCase,
    MarkLoyaltyCardBatchItemFailedUseCase,
    MarkLoyaltyCardBatchItemPrintedUseCase,
    StartLoyaltyCardBatchPrintingUseCase,
    SubmitLoyaltyCardBatchForApprovalUseCase,
)
from backend.application.loyalty_cards.use_cases.sheet_use_cases import (
    CreateImpositionProfileUseCase,
    CreateStandard12x18SheetProfileUseCase,
)
from backend.application.loyalty_cards.use_cases.template_use_cases import (
    ActivateLoyaltyCardTemplateVersionUseCase,
    ApproveLoyaltyCardTemplateUseCase,
    ApproveLoyaltyCardTemplateVersionUseCase,
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
    "elements": [],
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


def _active_template(conn, auth):
    create = CreateLoyaltyCardTemplateUseCase(auth).execute(
        conn, code="T1", name="Plantilla de lote", actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid())
    ApproveLoyaltyCardTemplateUseCase(auth).execute(
        conn, template_id=create.entity_id, actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid())
    version = CreateLoyaltyCardTemplateVersionUseCase(auth).execute(
        conn, template_id=create.entity_id, design_schema_json=_VALID_SCHEMA,
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    ApproveLoyaltyCardTemplateVersionUseCase(auth).execute(
        conn, version_id=version.entity_id, actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid())
    ActivateLoyaltyCardTemplateVersionUseCase(auth).execute(
        conn, version_id=version.entity_id, actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid())
    return create.entity_id


def _imposition_profile(conn, auth):
    sheet = CreateStandard12x18SheetProfileUseCase(auth).execute(
        conn, actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    imposition = CreateImpositionProfileUseCase(auth).execute(
        conn, sheet_profile_id=sheet.entity_id, card_width_mm=Decimal("85.6"),
        card_height_mm=Decimal("54"), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
        operation_id=new_uuid())
    return imposition.entity_id, imposition.data["cards_per_sheet"]


class TestCreateBatch:
    def test_create_issues_a_card_per_recipient(self, conn, auth):
        template_id = _active_template(conn, auth)
        imposition_id, cards_per_sheet = _imposition_profile(conn, auth)
        recipients = [(new_uuid(), new_uuid()) for _ in range(5)]
        result = CreateLoyaltyCardBatchUseCase(auth).execute(
            conn, template_id=template_id, imposition_profile_id=imposition_id,
            recipients=recipients, actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            operation_id=new_uuid())
        assert result.success
        expected_sheets = -(-5 // cards_per_sheet)
        assert result.data["sheets_required"] == expected_sheets
        with LoyaltyCardsUnitOfWork(conn) as uow:
            items = uow.batch_items.list_for_batch(result.entity_id)
            assert len(items) == 5
            for item in items:
                card = uow.cards.get(item.card_id)
                assert card is not None
                token = uow.tokens.get_active_for_card(card.id)
                assert token is not None

    def test_requires_active_template(self, conn, auth):
        create = CreateLoyaltyCardTemplateUseCase(auth).execute(
            conn, code="T2", name="Sin activar", actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        imposition_id, _ = _imposition_profile(conn, auth)
        result = CreateLoyaltyCardBatchUseCase(auth).execute(
            conn, template_id=create.entity_id, imposition_profile_id=imposition_id,
            recipients=[(new_uuid(), new_uuid())], actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "INVALID_BATCH"

    def test_template_not_found(self, conn, auth):
        imposition_id, _ = _imposition_profile(conn, auth)
        result = CreateLoyaltyCardBatchUseCase(auth).execute(
            conn, template_id=new_uuid(), imposition_profile_id=imposition_id,
            recipients=[(new_uuid(), new_uuid())], actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "TEMPLATE_NOT_FOUND"

    def test_empty_recipients_rejected(self, conn, auth):
        template_id = _active_template(conn, auth)
        imposition_id, _ = _imposition_profile(conn, auth)
        result = CreateLoyaltyCardBatchUseCase(auth).execute(
            conn, template_id=template_id, imposition_profile_id=imposition_id,
            recipients=[], actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "EMPTY_BATCH"


class TestBatchWorkflow:
    def _created_batch(self, conn, auth, *, count=3):
        template_id = _active_template(conn, auth)
        imposition_id, _ = _imposition_profile(conn, auth)
        recipients = [(new_uuid(), new_uuid()) for _ in range(count)]
        return CreateLoyaltyCardBatchUseCase(auth).execute(
            conn, template_id=template_id, imposition_profile_id=imposition_id,
            recipients=recipients, actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            operation_id=new_uuid())

    def test_full_workflow_completes_batch(self, conn, auth):
        batch = self._created_batch(conn, auth, count=2)
        SubmitLoyaltyCardBatchForApprovalUseCase(auth).execute(
            conn, batch_id=batch.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        ApproveLoyaltyCardBatchUseCase(auth).execute(
            conn, batch_id=batch.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        StartLoyaltyCardBatchPrintingUseCase(auth).execute(
            conn, batch_id=batch.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())

        with LoyaltyCardsUnitOfWork(conn) as uow:
            items = uow.batch_items.list_for_batch(batch.entity_id)
        for item in items[:-1]:
            result = MarkLoyaltyCardBatchItemPrintedUseCase(auth).execute(
                conn, item_id=item.id, actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
                operation_id=new_uuid())
            assert result.success
        with LoyaltyCardsUnitOfWork(conn) as uow:
            assert uow.batches.get(batch.entity_id).status.value == "PRINTING"

        MarkLoyaltyCardBatchItemPrintedUseCase(auth).execute(
            conn, item_id=items[-1].id, actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            operation_id=new_uuid())
        with LoyaltyCardsUnitOfWork(conn) as uow:
            assert uow.batches.get(batch.entity_id).status.value == "COMPLETED"

    def test_mark_item_failed(self, conn, auth):
        batch = self._created_batch(conn, auth, count=1)
        SubmitLoyaltyCardBatchForApprovalUseCase(auth).execute(
            conn, batch_id=batch.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        ApproveLoyaltyCardBatchUseCase(auth).execute(
            conn, batch_id=batch.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        StartLoyaltyCardBatchPrintingUseCase(auth).execute(
            conn, batch_id=batch.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        with LoyaltyCardsUnitOfWork(conn) as uow:
            item = uow.batch_items.list_for_batch(batch.entity_id)[0]
        result = MarkLoyaltyCardBatchItemFailedUseCase(auth).execute(
            conn, item_id=item.id, reason="atasco de impresora", actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success

    def test_cancel_batch(self, conn, auth):
        batch = self._created_batch(conn, auth, count=1)
        result = CancelLoyaltyCardBatchUseCase(auth).execute(
            conn, batch_id=batch.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success

    def test_batch_not_found(self, conn, auth):
        result = ApproveLoyaltyCardBatchUseCase(auth).execute(
            conn, batch_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "BATCH_NOT_FOUND"
