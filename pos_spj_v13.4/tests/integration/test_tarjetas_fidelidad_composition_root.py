"""LOY-25 — Tarjetas Fidelidad composition root against a REAL sqlite
connection (mirrors ``tests/integration/test_fidelidad_composition_root.py``'s
approach)."""

from __future__ import annotations

import os
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable",
                    exc_type=ImportError)

from backend.infrastructure.db.schema.loyalty_cards_schema import create_loyalty_cards_schema
from backend.shared.ids import new_uuid
from frontend.desktop.modules.tarjetas_fidelidad.composition import (
    build_tarjetas_fidelidad_presenter,
)


class _Session:
    is_active = True

    def __init__(self, user_id: str, branch_id: str) -> None:
        self.user_id = user_id
        self.active_branch_id = branch_id

    def tiene_permiso(self, _permission: str) -> bool:
        return True


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    create_loyalty_cards_schema(connection)
    connection.commit()
    yield connection
    connection.close()


class TestTarjetasFidelidadCompositionRoot:
    def test_issue_activate_block_unblock_end_to_end(self, conn):
        presenter = build_tarjetas_fidelidad_presenter(conn, _Session(new_uuid(), new_uuid()))
        issued = presenter.issue_card(customer_id=new_uuid(), membership_id=new_uuid())
        assert issued.success
        card_number = issued.data["card_number"]

        card = presenter.find_card_by_number(card_number)
        assert card is not None
        assert card.status.value == "ISSUED"

        assert presenter.activate_card(issued.entity_id).success
        card = presenter.find_card_by_number(card_number)
        assert card.status.value == "ACTIVE"

        blocked = presenter.block_card(card_id=issued.entity_id, reason="reportada perdida")
        assert blocked.success
        card = presenter.find_card_by_number(card_number)
        assert card.status.value == "BLOCKED"

        assert presenter.unblock_card(issued.entity_id).success
        card = presenter.find_card_by_number(card_number)
        assert card.status.value == "ACTIVE"

    def test_template_and_version_lifecycle_end_to_end(self, conn):
        import json

        presenter = build_tarjetas_fidelidad_presenter(conn, _Session(new_uuid(), new_uuid()))
        create = presenter.create_template(code="T1", name="Plantilla clásica")
        assert create.success

        approver = build_tarjetas_fidelidad_presenter(conn, _Session(new_uuid(), new_uuid()))
        assert approver.approve_template(create.entity_id).success

        schema = json.dumps({
            "canvas": {"width_mm": "85.6", "height_mm": "54", "background_color": "#FFFFFF"},
            "elements": [],
        })
        version = presenter.create_template_version(
            template_id=create.entity_id, design_schema_json=schema)
        assert version.success

        assert approver.approve_template_version(version.entity_id).success
        activated = approver.activate_template_version(version.entity_id)
        assert activated.success
