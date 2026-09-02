"""LOY-25 — Fidelidad composition root against a REAL sqlite connection
(mirrors ``tests/integration/customers/test_customers_crm_composition_root.py``'s
approach: verify every query service/command handler the composition root
wires is actually backed by real, working backend use cases — not just
presenter unit logic with fakes)."""

from __future__ import annotations

import os
import sqlite3
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable",
                    exc_type=ImportError)

from backend.infrastructure.db.schema.commercial_instruments_schema import (
    create_commercial_instruments_schema,
)
from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema
from backend.infrastructure.db.schema.sweepstakes_schema import create_sweepstakes_schema
from backend.shared.ids import new_uuid
from frontend.desktop.modules.fidelidad.composition import build_fidelidad_presenter


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
    create_loyalty_schema(connection)
    create_commercial_instruments_schema(connection)
    create_sweepstakes_schema(connection)
    connection.commit()
    yield connection
    connection.close()


class TestFidelidadCompositionRoot:
    def test_program_lifecycle_end_to_end(self, conn):
        presenter = build_fidelidad_presenter(conn, _Session(new_uuid(), new_uuid()))
        create = presenter.create_program(code="PTS", name="Puntos SPJ", currency_name="Estrellas")
        assert create.success
        assert presenter.list_programs() == []  # PENDING_APPROVAL, not ACTIVE yet

        approver = build_fidelidad_presenter(conn, _Session(new_uuid(), new_uuid()))
        assert approver.approve_program(create.entity_id).success
        assert approver.activate_program(create.entity_id).success
        assert [p.code for p in presenter.list_programs()] == ["PTS"]

    def test_member_profile_reflects_real_ledger(self, conn):
        actor = _Session(new_uuid(), new_uuid())
        presenter = build_fidelidad_presenter(conn, actor)
        create = presenter.create_program(code="PTS", name="Puntos", currency_name="Estrellas")
        approver = build_fidelidad_presenter(conn, _Session(new_uuid(), new_uuid()))
        approver.approve_program(create.entity_id)
        approver.activate_program(create.entity_id)

        customer_id = new_uuid()
        enroll = presenter.enroll_membership(customer_id=customer_id, program_id=create.entity_id)
        assert enroll.success

        view_before = presenter.member_profile(customer_id)
        assert view_before.found
        assert view_before.balance == Decimal("0")

        accrue = presenter.accrue_points(
            loyalty_account_id=view_before.account.id, points_amount=Decimal("100"),
            reason_code="Bono de bienvenida")
        assert accrue.success

        view_after = presenter.member_profile(customer_id)
        assert view_after.balance == Decimal("100")
        assert len(view_after.recent_transactions) == 1

    def test_sweepstakes_campaign_lifecycle_end_to_end(self, conn):
        presenter = build_fidelidad_presenter(conn, _Session(new_uuid(), new_uuid()))
        create = presenter.create_sweepstakes_campaign(code="RIFA1", name="Rifa de prueba")
        assert create.success
        assert presenter.list_sweepstakes_campaigns() == []

        approver = build_fidelidad_presenter(conn, _Session(new_uuid(), new_uuid()))
        assert approver.approve_sweepstakes_campaign(create.entity_id).success
        assert approver.activate_sweepstakes_campaign(create.entity_id).success
        assert [c.code for c in presenter.list_sweepstakes_campaigns()] == ["RIFA1"]

        prize = presenter.add_sweepstakes_prize(campaign_id=create.entity_id, name="Televisor")
        assert prize.success

        customer_id = new_uuid()
        entry = presenter.grant_sweepstakes_entry(
            campaign_id=create.entity_id, customer_id=customer_id)
        assert entry.success

        ticket = presenter.issue_sweepstakes_ticket(
            campaign_id=create.entity_id, entry_id=entry.entity_id)
        assert ticket.success
        assert ticket.data["ticket_number"] == "RIFA1-000001"

    def test_issue_coupon_end_to_end(self, conn):
        from decimal import Decimal as D

        from backend.domain.commercial_instruments.entities.coupon_definition import (
            CouponDefinition,
        )
        from backend.domain.commercial_instruments.enums import (
            CommercialBenefitType,
            CouponType,
        )
        from backend.infrastructure.db.repositories.commercial_instruments.coupon_repository import (
            CouponDefinitionRepository,
        )

        definition = CouponDefinition.create(
            "DESC10", "10% de descuento", CouponType.PUBLIC_CODE,
            CommercialBenefitType.PERCENTAGE, D("10"))
        CouponDefinitionRepository(conn).save(definition)

        presenter = build_fidelidad_presenter(conn, _Session(new_uuid(), new_uuid()))
        result = presenter.issue_coupon(definition_id=definition.id, customer_id=new_uuid())
        assert result.success
        assert result.data["instance"].code.startswith("CUP-")
