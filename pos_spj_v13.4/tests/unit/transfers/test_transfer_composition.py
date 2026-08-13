"""INV-12 — TransferUseCaseFactory composition root."""
import sqlite3

import pytest

from backend.application.transfers.composition import TransferUseCaseFactory
from backend.domain.transfers.exceptions import TransferConfigurationError
from backend.infrastructure.db.schema.transfers_schema import create_transfers_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_transfers_schema(c)
    c.commit()
    yield c
    c.close()


class _ActiveSession:
    user_id = "u1"
    is_active = True
    active_branch_id = "b1"

    def tiene_permiso(self, code: str) -> bool:
        return code in {"TRANSFERENCIAS.ver", "TRANSFERENCIAS.crear"}


class TestFailClosedConstruction:
    def test_none_permission_checker_raises(self, conn):
        with pytest.raises(TransferConfigurationError):
            TransferUseCaseFactory(connection=conn, permission_checker=None)

    def test_for_tests_builds_with_allow_all_checker(self, conn):
        factory = TransferUseCaseFactory.for_tests(connection=conn)
        assert factory.authorization_policy is not None

    def test_from_session_wires_the_real_session_checker(self, conn):
        factory = TransferUseCaseFactory.from_session(_ActiveSession(), connection=conn)
        assert factory.authorization_policy is not None


class TestCreateTransferRequest:
    def test_builds_a_working_use_case_against_the_real_repository(self, conn):
        from decimal import Decimal

        from backend.application.transfers.commands.transfer_request_commands import (
            CreateTransferRequestCommand, TransferRequestLineCommand,
        )
        from backend.domain.transfers.enums import TransferNodeType, TransferType
        from backend.domain.transfers.value_objects.transfer_node import TransferNode

        factory = TransferUseCaseFactory.for_tests(connection=conn)
        uc = factory.create_transfer_request()
        dto = uc.execute(CreateTransferRequestCommand(
            requested_by_user_id="u1", operation_id="op-1",
            transfer_type=TransferType.BRANCH_TO_BRANCH,
            origin_node=TransferNode(TransferNodeType.BRANCH, branch_id="b1"),
            destination_node=TransferNode(TransferNodeType.BRANCH, branch_id="b2"),
            lines=(TransferRequestLineCommand(
                product_id="p1", unit_id="unit-kg", requested_quantity=Decimal("5")),)))

        assert dto.transfer_number.startswith("TRF-")
        row = conn.execute(
            "SELECT status FROM stock_transfers WHERE id = ?", (dto.transfer_id,)).fetchone()
        assert row["status"] == "DRAFT"
