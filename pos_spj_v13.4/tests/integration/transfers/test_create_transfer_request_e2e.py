"""INV-12 — Create Transfer Request, full stack: presenter -> composition root
-> use case -> repository -> DB. Exercises the exact path
``TransfersModuleHost`` wires in production (minus the Qt dialog itself)."""
from decimal import Decimal

import sqlite3

import pytest

from backend.application.transfers.composition import TransferUseCaseFactory
from backend.infrastructure.db.repositories.transfers.transfer_query_repository import (
    TransferWorkspaceQueryRepository,
)
from backend.infrastructure.db.schema.transfers_schema import create_transfers_schema
from frontend.desktop.modules.transfers.transfers_presenter import TransfersPresenter


class _Session:
    user_id = "u1"
    is_active = True
    active_branch_id = "b1"

    def tiene_permiso(self, code: str) -> bool:
        return code in {"TRANSFERENCIAS.ver", "TRANSFERENCIAS.crear"}


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_transfers_schema(c)
    c.execute("CREATE TABLE sucursales (id TEXT PRIMARY KEY, nombre TEXT, activa INTEGER)")
    c.execute("INSERT INTO sucursales VALUES ('b1', 'Matriz', 1), ('b2', 'Sucursal Centro', 1)")
    c.execute("CREATE TABLE products (id TEXT PRIMARY KEY, base_unit_id TEXT)")
    c.execute("INSERT INTO products VALUES ('p1', 'unit-kg')")
    c.commit()
    yield c
    c.close()


def _presenter(conn, *, session=_Session()):
    factory = TransferUseCaseFactory.from_session(session, connection=conn)
    return TransfersPresenter(
        query_service=TransferWorkspaceQueryRepository(conn), connection=conn,
        create_transfer_request_uc=factory.create_transfer_request(), session_context=session)


class TestCreateTransferRequestEndToEnd:
    def test_creates_a_draft_transfer_with_a_unique_number(self, conn):
        presenter = _presenter(conn)
        ok, message, data = presenter.create_transfer_request(
            origin_branch_id="b1", destination_branch_id="b2", product_id="p1",
            quantity=Decimal("10"), weight=Decimal("2"))

        assert ok is True
        assert data["transfer_number"].startswith("TRF-")
        row = conn.execute(
            "SELECT status, requested_by_user_id FROM stock_transfers WHERE id = ?",
            (data["transfer_id"],)).fetchone()
        assert row["status"] == "DRAFT"
        assert row["requested_by_user_id"] == "u1"
        line = conn.execute(
            "SELECT unit_id, requested_quantity FROM stock_transfer_lines WHERE transfer_id = ?",
            (data["transfer_id"],)).fetchone()
        assert line["unit_id"] == "unit-kg"
        assert line["requested_quantity"] == "10"

    def test_second_request_gets_a_different_sequential_number(self, conn):
        presenter = _presenter(conn)
        _, _, first = presenter.create_transfer_request(
            origin_branch_id="b1", destination_branch_id="b2", product_id="p1", quantity=Decimal("1"))
        _, _, second = presenter.create_transfer_request(
            origin_branch_id="b1", destination_branch_id="b2", product_id="p1", quantity=Decimal("1"))
        assert first["transfer_number"] != second["transfer_number"]

    def test_same_origin_and_destination_is_rejected(self, conn):
        presenter = _presenter(conn)
        ok, message, _ = presenter.create_transfer_request(
            origin_branch_id="b1", destination_branch_id="b1", product_id="p1", quantity=Decimal("1"))
        assert ok is False
        assert "distintos" in message

    def test_unauthorized_user_is_denied_fail_closed(self, conn):
        class _NoPermissionSession(_Session):
            def tiene_permiso(self, code: str) -> bool:
                return False

        presenter = _presenter(conn, session=_NoPermissionSession())
        ok, message, _ = presenter.create_transfer_request(
            origin_branch_id="b1", destination_branch_id="b2", product_id="p1", quantity=Decimal("1"))
        assert ok is False

    def test_branch_options_lists_active_branches(self, conn):
        presenter = _presenter(conn)
        options = presenter.branch_options()
        assert {o.id for o in options} == {"b1", "b2"}
