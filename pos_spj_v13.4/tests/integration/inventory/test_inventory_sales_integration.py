"""INV-11 — Sales/POS integration e2e over the canonical inventory context.

POS reads availability (never writes stock); a confirmed sale drives a SALE_ISSUE
movement (live path: CanonicalSaleInventoryHandler, exercised elsewhere — here we
post the same movement type directly to set up return scenarios); a customer
return drives a SALE_RETURN into PENDING_INSPECTION (Quality intervenes). All
idempotent by operation_id.
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.event_handlers.inventory.customer_return_handler import (
    CustomerReturnHandler,
)
from backend.application.inventory.queries import InventoryAvailabilityQueryService
from backend.application.inventory.use_cases import (
    CreateReservationUseCase,
    PostInventoryMovementUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import InventoryStatus, MovementType, ReservationSource
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _receipt(conn, qty="10", loc="loc1", op="r1"):
    line = InventoryMovementLine.create(product_id="p1", quantity=Decimal(qty),
                                        to_location_id=loc)
    mv = InventoryMovement.create(
        movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id="w1",
        source_module="procurement", source_document_type="GR", source_document_id="gr1",
        operation_id=op, created_by_user_id="u1", lines=[line])
    PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")


def _issue(conn, qty="4", loc="loc1", op="sale-1"):
    line = InventoryMovementLine.create(product_id="p1", quantity=Decimal(qty),
                                        from_location_id=loc)
    mv = InventoryMovement.create(
        movement_type=MovementType.SALE_ISSUE, branch_id="b1", warehouse_id="w1",
        source_module="sales", source_document_type="SALE", source_document_id="SALE-1",
        operation_id=op, created_by_user_id="u1", lines=[line])
    PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")


def _avail(conn):
    return InventoryAvailabilityQueryService(conn).get_availability(
        product_id="p1", branch_id="b1")


class TestAvailabilityQuery:
    def test_available_is_on_hand_minus_reserved(self, conn):
        _receipt(conn, "10")
        assert _avail(conn).available == Decimal("10")
        CreateReservationUseCase().execute(
            conn, product_id="p1", branch_id="b1", warehouse_id="w1",
            source=ReservationSource.SALE, source_document_id="s1", quantity=Decimal("4"),
            operation_id="res-1", actor_user_id="u1", location_id="loc1")
        dto = _avail(conn)
        assert dto.on_hand == Decimal("10") and dto.reserved == Decimal("4")
        assert dto.available == Decimal("6")

    def test_is_available_helper(self, conn):
        _receipt(conn, "5")
        svc = InventoryAvailabilityQueryService(conn)
        assert svc.is_available(product_id="p1", branch_id="b1", quantity=Decimal("5"))
        assert not svc.is_available(product_id="p1", branch_id="b1", quantity=Decimal("6"))

    def test_by_status_breakdown(self, conn):
        _receipt(conn, "10")
        assert _avail(conn).by_status["AVAILABLE"] == "10"


class TestCustomerReturnHandler:
    def test_return_enters_pending_inspection(self, conn):
        _receipt(conn, "10")
        _issue(conn, "4")
        CustomerReturnHandler(conn).handle(
            {"operation_id": "ret-1", "branch_id": "b1", "warehouse_id": "w1",
             "document_id": "RET-1", "user_id": "c",
             "lines": [{"product_id": "p1", "quantity": "2", "to_location_id": "loc1"}]})
        dto = _avail(conn)
        # returned stock is NOT immediately available (Quality must inspect)
        assert dto.available == Decimal("6")
        assert dto.by_status.get("PENDING_INSPECTION") == "2"
