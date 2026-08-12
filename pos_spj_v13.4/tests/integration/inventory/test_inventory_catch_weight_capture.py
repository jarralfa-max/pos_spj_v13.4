"""INV-8 — RecordCatchWeightUseCase e2e: scale/manual capture applied as an
inventory adjustment (reason=WEIGHT_VARIANCE), plus the AdjustmentQueryService
reason filter that powers "Ver historial" (§28/§29)."""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.queries.adjustment_query_service import (
    AdjustmentQueryService,
)
from backend.application.inventory.use_cases.adjustment_use_cases import (
    CreateAdjustmentUseCase,
)
from backend.application.inventory.use_cases.catch_weight_use_cases import (
    RecordCatchWeightUseCase,
)
from backend.domain.inventory.enums import AdjustmentReason
from backend.domain.inventory.value_objects.catch_weight import WeightReading
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.hardware.scale_gateway import StubScaleGateway


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


class TestScalePath:
    def test_stable_reading_posts_adjustment(self, conn):
        gateway = StubScaleGateway([WeightReading(gross=Decimal("58.75"), stable=True)])
        r = RecordCatchWeightUseCase().execute(
            conn, product_id="p1", branch_id="b1", warehouse_id="w1",
            operation_id="op-1", actor_user_id="u1", gateway=gateway,
            min_weight=Decimal("1"), max_weight=Decimal("100"))
        assert r.success
        assert r.data["weight_reading"]["net"] == "58.75"
        with InventoryUnitOfWork(conn) as uow:
            adj = uow.adjustments.get(r.entity_id)
            assert adj.reason is AdjustmentReason.WEIGHT_VARIANCE
            assert adj.lines[0].weight_delta == Decimal("58.75")

    def test_unstable_reading_rejected(self, conn):
        gateway = StubScaleGateway([WeightReading(gross=Decimal("58"), stable=False)])
        r = RecordCatchWeightUseCase().execute(
            conn, product_id="p1", branch_id="b1", warehouse_id="w1",
            operation_id="op-1", actor_user_id="u1", gateway=gateway)
        assert not r.success and r.error_code == "INVALID_WEIGHT_READING"


class TestManualPath:
    def test_missing_gross_rejected(self, conn):
        r = RecordCatchWeightUseCase().execute(
            conn, product_id="p1", branch_id="b1", warehouse_id="w1",
            operation_id="op-1", actor_user_id="u1")
        assert not r.success and r.error_code == "WEIGHT_REQUIRED"

    def test_in_range_posts_adjustment(self, conn):
        r = RecordCatchWeightUseCase().execute(
            conn, product_id="p1", branch_id="b1", warehouse_id="w1",
            operation_id="op-1", actor_user_id="u1", gross=Decimal("5"),
            pieces_delta=Decimal("2"))
        assert r.success
        with InventoryUnitOfWork(conn) as uow:
            adj = uow.adjustments.get(r.entity_id)
            assert adj.lines[0].weight_delta == Decimal("5")
            assert adj.lines[0].quantity_delta == Decimal("2")

    def test_out_of_range_without_authorizer_fails(self, conn):
        r = RecordCatchWeightUseCase().execute(
            conn, product_id="p1", branch_id="b1", warehouse_id="w1",
            operation_id="op-1", actor_user_id="u1", gross=Decimal("20"),
            max_weight=Decimal("10"))
        assert not r.success and r.error_code == "PERMISSION_DENIED"

    def test_out_of_range_same_user_authorizer_fails_sod(self, conn):
        r = RecordCatchWeightUseCase().execute(
            conn, product_id="p1", branch_id="b1", warehouse_id="w1",
            operation_id="op-1", actor_user_id="u1", gross=Decimal("20"),
            max_weight=Decimal("10"), authorizer_user_id="u1")
        assert not r.success and r.error_code == "SEGREGATION_OF_DUTIES"

    def test_out_of_range_distinct_authorizer_posts_adjustment(self, conn):
        r = RecordCatchWeightUseCase().execute(
            conn, product_id="p1", branch_id="b1", warehouse_id="w1",
            operation_id="op-1", actor_user_id="u1", gross=Decimal("20"),
            max_weight=Decimal("10"), authorizer_user_id="boss")
        assert r.success
        with InventoryUnitOfWork(conn) as uow:
            adj = uow.adjustments.get(r.entity_id)
            assert adj.reason is AdjustmentReason.WEIGHT_VARIANCE
            assert adj.lines[0].weight_delta == Decimal("20")


class TestPermissions:
    def test_weight_capture_denied(self, conn):
        class Deny:
            def has_permission(self, u, p):
                return False
        r = RecordCatchWeightUseCase(InventoryAuthorizationPolicy(Deny())).execute(
            conn, product_id="p1", branch_id="b1", warehouse_id="w1",
            operation_id="op-1", actor_user_id="u1", gross=Decimal("5"))
        assert not r.success and r.error_code == "PERMISSION_DENIED"

    def test_adjustment_create_denied(self, conn):
        class AllowCaptureOnly:
            def has_permission(self, u, p):
                return p != InventoryPermissions.ADJUSTMENT_CREATE
        r = RecordCatchWeightUseCase(
            InventoryAuthorizationPolicy(AllowCaptureOnly())).execute(
            conn, product_id="p1", branch_id="b1", warehouse_id="w1",
            operation_id="op-1", actor_user_id="u1", gross=Decimal("5"))
        assert not r.success and r.error_code == "PERMISSION_DENIED"


class TestAdjustmentQueryReasonFilter:
    def test_list_recent_filters_by_reason(self, conn):
        CreateAdjustmentUseCase().execute(
            conn, folio="AJ-1", branch_id="b1", warehouse_id="w1",
            reason=AdjustmentReason.DAMAGE,
            lines=[{"product_id": "p1", "quantity_delta": Decimal("-1")}],
            operation_id="op-a", actor_user_id="u1")
        RecordCatchWeightUseCase().execute(
            conn, product_id="p1", branch_id="b1", warehouse_id="w1",
            operation_id="op-b", actor_user_id="u1", gross=Decimal("5"))
        rows = AdjustmentQueryService(conn).list_recent(
            branch_id="b1", reason="WEIGHT_VARIANCE")
        assert len(rows) == 1
        assert rows[0]["reason"] == "WEIGHT_VARIANCE"
