"""PROC-9 e2e: weighing capture (incl. manual override hot authorization),
consumption capture (incl. tolerance override), and posting via
InventoryConsumptionPort."""

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.application.meat_processing.authorization import (
    AllowAllMeatProcessingPermissionCheckerForTests,
    MeatProcessingAuthorizationPolicy,
)
from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.application.meat_processing.use_cases import (
    ApproveProcessingOrderUseCase,
    CaptureMaterialConsumptionUseCase,
    CaptureProcessWeighingUseCase,
    CreateProcessingOrderUseCase,
    PostMaterialConsumptionUseCase,
)
from backend.domain.meat_processing.enums import ConsumptionStatus, ProcessType, WeighingType
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    importlib.import_module(
        "migrations.standalone.187_meat_processing_bounded_context_schema").run(c)
    importlib.import_module(
        "migrations.standalone.248_meat_processing_preparation_execution_schema").run(c)
    yield c
    c.close()


@pytest.fixture
def approved_order_id(conn):
    created = CreateProcessingOrderUseCase().execute(
        conn, operation_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(),
        process_type=ProcessType.CUTTING, target_product_id=new_uuid(),
        planned_quantity=Decimal("10"), planned_weight=Decimal("100"),
        actor_user_id=new_uuid())
    ApproveProcessingOrderUseCase().execute(
        conn, order_id=created.entity_id, operation_id=new_uuid(), actor_user_id=new_uuid())
    return created.entity_id


class TestWeighing:
    def test_capture_stable_weight(self, conn, approved_order_id):
        result = CaptureProcessWeighingUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(),
            weighing_type=WeighingType.INPUT, gross_weight=Decimal("100"),
            tare_weight=Decimal("5"), actor_user_id=new_uuid())
        assert result.success
        assert result.data["net_weight"] == "95"

    def test_manual_override_without_authorization_permission_is_denied(
            self, conn, approved_order_id):
        class CaptureOnlyChecker:
            """Allows WEIGHT_CAPTURE but denies WEIGHT_MANUAL_OVERRIDE — an
            actor who can weigh but isn't trusted to authorize an override."""

            def has_permission(self, user_id, permission_code):
                return permission_code == MeatProcessingPermissions.WEIGHT_CAPTURE

        use_case = CaptureProcessWeighingUseCase(
            MeatProcessingAuthorizationPolicy(CaptureOnlyChecker()))
        result = use_case.execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(),
            weighing_type=WeighingType.INPUT, gross_weight=Decimal("100"),
            actor_user_id=new_uuid(), stable=False, manual_override=True,
            authorized_by_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "PERMISSION_DENIED"

    def test_manual_override_with_authorization_records_grant(self, conn, approved_order_id):
        authorizer = new_uuid()
        use_case = CaptureProcessWeighingUseCase(
            MeatProcessingAuthorizationPolicy(AllowAllMeatProcessingPermissionCheckerForTests()))
        result = use_case.execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(),
            weighing_type=WeighingType.INPUT, gross_weight=Decimal("100"),
            actor_user_id=new_uuid(), stable=False, manual_override=True,
            authorized_by_user_id=authorizer, override_reason="Báscula inestable")
        assert result.success
        with MeatProcessingUnitOfWork(conn) as uow:
            rows = uow.authorization_log._query(
                "SELECT * FROM meat_processing_authorization_log WHERE authorized_by=?",
                (authorizer,))
            assert len(rows) == 1
            assert rows[0]["permission_code"] == MeatProcessingPermissions.WEIGHT_MANUAL_OVERRIDE

    def test_unstable_weight_without_override_is_rejected_by_domain(self, conn, approved_order_id):
        result = CaptureProcessWeighingUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(),
            weighing_type=WeighingType.INPUT, gross_weight=Decimal("100"),
            actor_user_id=new_uuid(), stable=False, manual_override=False)
        assert not result.success
        assert result.error_code == "MEAT_PROCESSING_RULE_VIOLATION"


class TestConsumption:
    def test_capture_within_tolerance(self, conn, approved_order_id):
        result = CaptureMaterialConsumptionUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), product_id=new_uuid(),
            warehouse_id=new_uuid(), planned_quantity=Decimal("100"),
            planned_weight=Decimal("100"), actual_quantity=Decimal("102"),
            actual_weight=Decimal("102"), actor_user_id=new_uuid(),
            tolerance_pct=Decimal("5"))
        assert result.success
        assert result.data["status"] == ConsumptionStatus.PENDING_POSTING.value

    def test_capture_over_tolerance_without_authorizer_fails(self, conn, approved_order_id):
        result = CaptureMaterialConsumptionUseCase().execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), product_id=new_uuid(),
            warehouse_id=new_uuid(), planned_quantity=Decimal("100"),
            planned_weight=Decimal("100"), actual_quantity=Decimal("120"),
            actual_weight=Decimal("100"), actor_user_id=new_uuid(),
            tolerance_pct=Decimal("5"))
        assert not result.success
        assert result.error_code == "MEAT_PROCESSING_RULE_VIOLATION"

    def test_capture_over_tolerance_with_authorized_override_succeeds(
            self, conn, approved_order_id):
        use_case = CaptureMaterialConsumptionUseCase(
            MeatProcessingAuthorizationPolicy(AllowAllMeatProcessingPermissionCheckerForTests()))
        result = use_case.execute(
            conn, order_id=approved_order_id, operation_id=new_uuid(), product_id=new_uuid(),
            warehouse_id=new_uuid(), planned_quantity=Decimal("100"),
            planned_weight=Decimal("100"), actual_quantity=Decimal("120"),
            actual_weight=Decimal("100"), actor_user_id=new_uuid(),
            tolerance_pct=Decimal("5"), authorized_by_user_id=new_uuid(),
            override_reason="Merma justificada")
        assert result.success


class TestPosting:
    def _pending_consumption_id(self, conn, order_id):
        captured = CaptureMaterialConsumptionUseCase().execute(
            conn, order_id=order_id, operation_id=new_uuid(), product_id=new_uuid(),
            warehouse_id=new_uuid(), planned_quantity=Decimal("10"),
            planned_weight=Decimal("100"), actual_quantity=Decimal("10"),
            actual_weight=Decimal("100"), actor_user_id=new_uuid())
        return captured.entity_id

    def test_post_without_inventory_port_reports_pending_integration(
            self, conn, approved_order_id):
        consumption_id = self._pending_consumption_id(conn, approved_order_id)
        result = PostMaterialConsumptionUseCase().execute(
            conn, consumption_id=consumption_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "INVENTORY_INTEGRATION_PENDING"

    def test_post_with_fake_inventory_port_succeeds_and_is_idempotent(
            self, conn, approved_order_id):
        consumption_id = self._pending_consumption_id(conn, approved_order_id)

        class FakePort:
            def post_consumption(self, **kwargs):
                return new_uuid()

        use_case = PostMaterialConsumptionUseCase(inventory_port=FakePort())
        first = use_case.execute(
            conn, consumption_id=consumption_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert first.success
        with MeatProcessingUnitOfWork(conn) as uow:
            assert uow.consumptions.get(consumption_id).status is ConsumptionStatus.POSTED

        second = use_case.execute(
            conn, consumption_id=consumption_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())
        assert second.data["already_processed"] is True

    def test_post_unknown_consumption_fails(self, conn):
        result = PostMaterialConsumptionUseCase().execute(
            conn, consumption_id=new_uuid(), operation_id=new_uuid(), actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "CONSUMPTION_NOT_FOUND"
