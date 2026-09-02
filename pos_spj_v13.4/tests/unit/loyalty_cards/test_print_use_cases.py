"""LOY-22 — Loyalty Card batch printing use cases (master prompt §50-51)."""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal

import pytest

from backend.application.loyalty_cards.authorization import LoyaltyCardsAuthorizationPolicy
from backend.application.loyalty_cards.use_cases.batch_use_cases import CreateLoyaltyCardBatchUseCase
from backend.application.loyalty_cards.use_cases.print_use_cases import (
    ReprintLoyaltyCardBatchUseCase,
    RenderLoyaltyCardBatchUseCase,
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
from backend.domain.loyalty_cards.enums import LoyaltyCardPrintJobStatus
from backend.infrastructure.db.repositories.loyalty_cards.unit_of_work import (
    LoyaltyCardsUnitOfWork,
)
from backend.infrastructure.db.schema.loyalty_cards_schema import create_loyalty_cards_schema
from backend.shared.ids import new_uuid

_DESIGN_SCHEMA = json.dumps({
    "canvas": {"width_mm": "85.6", "height_mm": "54", "background_color": "#FFFFFF"},
    "elements": [
        {"type": "TEXT", "x_mm": "5", "y_mm": "5", "width_mm": "50", "height_mm": "8",
         "content": "{{customer_name}}"},
        {"type": "QR", "x_mm": "60", "y_mm": "5", "width_mm": "20", "height_mm": "20",
         "data_source": "CARD_TOKEN"},
        {"type": "BARCODE", "x_mm": "5", "y_mm": "40", "width_mm": "50", "height_mm": "10",
         "format": "CODE128", "data_source": "CARD_NUMBER"},
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


def _active_template(conn, auth):
    create = CreateLoyaltyCardTemplateUseCase(auth).execute(
        conn, code="T1", name="Plantilla de impresión", actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid())
    ApproveLoyaltyCardTemplateUseCase(auth).execute(
        conn, template_id=create.entity_id, actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid())
    version = CreateLoyaltyCardTemplateVersionUseCase(auth).execute(
        conn, template_id=create.entity_id, design_schema_json=_DESIGN_SCHEMA,
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
    return imposition.entity_id


def _batch_with_cards(conn, auth, *, count=2):
    template_id = _active_template(conn, auth)
    imposition_id = _imposition_profile(conn, auth)
    recipients = [(new_uuid(), new_uuid()) for _ in range(count)]
    batch = CreateLoyaltyCardBatchUseCase(auth).execute(
        conn, template_id=template_id, imposition_profile_id=imposition_id, recipients=recipients,
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    with LoyaltyCardsUnitOfWork(conn) as uow:
        items = uow.batch_items.list_for_batch(batch.entity_id)
        placeholder_values = {
            item.card_id: {
                "customer_name": f"Cliente {i}",
                "card_token": f"tok-{i}",
                "card_number": uow.cards.get(item.card_id).card_number,
            }
            for i, item in enumerate(items)
        }
    return batch.entity_id, placeholder_values


class TestRenderBatch:
    def test_render_produces_real_pdf_and_ready_job(self, conn, auth):
        batch_id, placeholder_values = _batch_with_cards(conn, auth, count=3)
        result = RenderLoyaltyCardBatchUseCase(auth).execute(
            conn, batch_id=batch_id, card_placeholder_values=placeholder_values,
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["pdf_size_bytes"] > 0
        assert result.data["sheets_rendered"] == 1

        with LoyaltyCardsUnitOfWork(conn) as uow:
            job = uow.print_jobs.get(result.entity_id)
        assert job.status is LoyaltyCardPrintJobStatus.READY
        assert job.batch_id == batch_id

    def test_missing_placeholder_fails_job(self, conn, auth):
        batch_id, _ = _batch_with_cards(conn, auth, count=1)
        result = RenderLoyaltyCardBatchUseCase(auth).execute(
            conn, batch_id=batch_id, card_placeholder_values={}, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "INVALID_DESIGN_SCHEMA"
        with LoyaltyCardsUnitOfWork(conn) as uow:
            jobs = uow.print_jobs.list_for_batch(batch_id)
        assert len(jobs) == 1
        assert jobs[0].status is LoyaltyCardPrintJobStatus.FAILED

    def test_batch_not_found(self, conn, auth):
        result = RenderLoyaltyCardBatchUseCase(auth).execute(
            conn, batch_id=new_uuid(), card_placeholder_values={}, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "BATCH_NOT_FOUND"

    def test_render_only_sheet_number_filters_units(self, conn, auth):
        batch_id, placeholder_values = _batch_with_cards(conn, auth, count=2)
        result = RenderLoyaltyCardBatchUseCase(auth).execute(
            conn, batch_id=batch_id, card_placeholder_values=placeholder_values,
            actor_user_id=new_uuid(), operation_id=new_uuid(), only_sheet_number=1)
        assert result.success
        assert result.data["sheets_rendered"] == 1


class TestReprintBatch:
    def test_reprint_creates_new_job_linked_to_original(self, conn, auth):
        batch_id, placeholder_values = _batch_with_cards(conn, auth, count=2)
        original = RenderLoyaltyCardBatchUseCase(auth).execute(
            conn, batch_id=batch_id, card_placeholder_values=placeholder_values,
            actor_user_id=new_uuid(), operation_id=new_uuid())
        result = ReprintLoyaltyCardBatchUseCase(auth).execute(
            conn, original_job_id=original.entity_id, reason="tarjeta dañada en impresión",
            card_placeholder_values=placeholder_values, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert result.success
        assert result.data["reprint_of_job_id"] == original.entity_id

        with LoyaltyCardsUnitOfWork(conn) as uow:
            reprint_job = uow.print_jobs.get(result.entity_id)
        assert reprint_job.reprint_of_job_id == original.entity_id
        assert reprint_job.reprint_reason == "tarjeta dañada en impresión"
        assert reprint_job.status is LoyaltyCardPrintJobStatus.READY

    def test_reprint_requires_reason(self, conn, auth):
        batch_id, placeholder_values = _batch_with_cards(conn, auth, count=1)
        original = RenderLoyaltyCardBatchUseCase(auth).execute(
            conn, batch_id=batch_id, card_placeholder_values=placeholder_values,
            actor_user_id=new_uuid(), operation_id=new_uuid())
        result = ReprintLoyaltyCardBatchUseCase(auth).execute(
            conn, original_job_id=original.entity_id, reason="",
            card_placeholder_values=placeholder_values, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success

    def test_reprint_original_not_found(self, conn, auth):
        result = ReprintLoyaltyCardBatchUseCase(auth).execute(
            conn, original_job_id=new_uuid(), reason="motivo", card_placeholder_values={},
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "PRINT_JOB_NOT_FOUND"
