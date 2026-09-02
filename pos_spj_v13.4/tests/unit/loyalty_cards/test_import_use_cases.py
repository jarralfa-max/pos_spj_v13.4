"""LOY-19 — ImportLoyaltyCardDesignUseCase (master prompt §41-42)."""

from __future__ import annotations

import sqlite3
from io import BytesIO

import pytest

from backend.application.loyalty_cards.authorization import LoyaltyCardsAuthorizationPolicy
from backend.application.loyalty_cards.use_cases.import_use_cases import (
    ImportLoyaltyCardDesignUseCase,
)
from backend.application.loyalty_cards.use_cases.template_use_cases import (
    ApproveLoyaltyCardTemplateUseCase,
    CreateLoyaltyCardTemplateUseCase,
)
from backend.infrastructure.db.repositories.loyalty_cards.unit_of_work import (
    LoyaltyCardsUnitOfWork,
)
from backend.infrastructure.db.schema.loyalty_cards_schema import create_loyalty_cards_schema
from backend.shared.ids import new_uuid


def _png_bytes(width: int, height: int) -> bytes:
    from PIL import Image
    buf = BytesIO()
    Image.new("RGB", (width, height), color="white").save(buf, format="PNG")
    return buf.getvalue()


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
        conn, code="T1", name="Plantilla importada", actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid())
    ApproveLoyaltyCardTemplateUseCase(auth).execute(
        conn, template_id=create.entity_id, actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid())
    return create.entity_id


class TestImportDesign:
    def test_import_png_creates_canvas_only_version(self, conn, auth):
        template_id = _approved_template(conn, auth)
        result = ImportLoyaltyCardDesignUseCase(auth).execute(
            conn, template_id=template_id, file_bytes=_png_bytes(1011, 638),
            source_format="PNG", actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            operation_id=new_uuid())
        assert result.success
        assert result.data["version_number"] == 1
        assert "width_mm" in result.data["canvas"]
        with LoyaltyCardsUnitOfWork(conn) as uow:
            version = uow.template_versions.get(result.entity_id)
            assert version.status.value == "DRAFT"

    def test_import_rejects_malicious_svg_before_touching_db(self, conn, auth):
        template_id = _approved_template(conn, auth)
        malicious = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1">' \
                    b"<script>alert(1)</script></svg>"
        result = ImportLoyaltyCardDesignUseCase(auth).execute(
            conn, template_id=template_id, file_bytes=malicious, source_format="SVG",
            actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "INVALID_DESIGN_SCHEMA"
        with LoyaltyCardsUnitOfWork(conn) as uow:
            assert uow.template_versions.count_for_template(template_id) == 0

    def test_import_template_not_found(self, conn, auth):
        result = ImportLoyaltyCardDesignUseCase(auth).execute(
            conn, template_id=new_uuid(), file_bytes=_png_bytes(100, 100),
            source_format="PNG", actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "TEMPLATE_NOT_FOUND"

    def test_import_pdf_not_implemented(self, conn, auth):
        template_id = _approved_template(conn, auth)
        result = ImportLoyaltyCardDesignUseCase(auth).execute(
            conn, template_id=template_id, file_bytes=b"%PDF-1.4", source_format="PDF",
            actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "INVALID_DESIGN_SCHEMA"

    def test_second_import_increments_version_number(self, conn, auth):
        template_id = _approved_template(conn, auth)
        ImportLoyaltyCardDesignUseCase(auth).execute(
            conn, template_id=template_id, file_bytes=_png_bytes(100, 100),
            source_format="PNG", actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            operation_id=new_uuid())
        result = ImportLoyaltyCardDesignUseCase(auth).execute(
            conn, template_id=template_id, file_bytes=_png_bytes(100, 100),
            source_format="PNG", actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            operation_id=new_uuid())
        assert result.data["version_number"] == 2
