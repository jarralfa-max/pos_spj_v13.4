"""PROC-13 e2e: packaging execution, label printing and reprinting."""

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.application.meat_processing.use_cases import (
    ApproveProcessingOrderUseCase,
    CreateProcessingOrderUseCase,
    ExecutePackagingUseCase,
    PrintProductionLabelUseCase,
    ReprintProductionLabelUseCase,
)
from backend.domain.meat_processing.enums import ProcessType
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
        "migrations.standalone.249_meat_processing_packaging_schema").run(c)
    yield c
    c.close()


@pytest.fixture
def approved_order_id(conn):
    created = CreateProcessingOrderUseCase().execute(
        conn, operation_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(),
        process_type=ProcessType.PACKAGING, target_product_id=new_uuid(),
        planned_quantity=Decimal("10"), planned_weight=Decimal("10"),
        actor_user_id=new_uuid())
    ApproveProcessingOrderUseCase().execute(
        conn, order_id=created.entity_id, operation_id=new_uuid(), actor_user_id=new_uuid())
    return created.entity_id


def _package(conn, order_id):
    return ExecutePackagingUseCase().execute(
        conn, order_id=order_id, operation_id=new_uuid(), product_id=new_uuid(),
        packaging_material_id=new_uuid(), package_quantity=20, net_weight=Decimal("9.5"),
        gross_weight=Decimal("10"), tare_weight=Decimal("0.5"), actor_user_id=new_uuid())


class TestExecutePackaging:
    def test_execute_packaging_succeeds(self, conn, approved_order_id):
        result = _package(conn, approved_order_id)
        assert result.success
        with MeatProcessingUnitOfWork(conn) as uow:
            packaging = uow.packaging_executions.get(result.entity_id)
            assert packaging.package_quantity == 20

    def test_execute_packaging_unknown_order_fails(self, conn):
        result = ExecutePackagingUseCase().execute(
            conn, order_id=new_uuid(), operation_id=new_uuid(), product_id=new_uuid(),
            packaging_material_id=new_uuid(), package_quantity=1, net_weight=Decimal("1"),
            gross_weight=Decimal("1"), actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "ORDER_NOT_FOUND"

    def test_execute_packaging_emits_event(self, conn, approved_order_id):
        result = _package(conn, approved_order_id)
        with MeatProcessingUnitOfWork(conn) as uow:
            pending = uow.outbox.list_pending()
            assert any(row["operation_id"] == result.operation_id for row in pending)


class TestLabelPrinting:
    def test_print_label_first_time(self, conn, approved_order_id):
        packaging_id = _package(conn, approved_order_id).entity_id
        result = PrintProductionLabelUseCase().execute(
            conn, packaging_execution_id=packaging_id, operation_id=new_uuid(),
            label_template_id=new_uuid(), barcode="7501234567890",
            qr_traceability_reference="LPR-2026-000001", actor_user_id=new_uuid())
        assert result.success
        with MeatProcessingUnitOfWork(conn) as uow:
            label = uow.production_labels.get(result.entity_id)
            assert label.is_printed
            assert label.reprint_count == 0

    def test_print_label_is_idempotent_on_operation_id(self, conn, approved_order_id):
        packaging_id = _package(conn, approved_order_id).entity_id
        op_id = new_uuid()
        first = PrintProductionLabelUseCase().execute(
            conn, packaging_execution_id=packaging_id, operation_id=op_id,
            label_template_id=new_uuid(), barcode="1", qr_traceability_reference="ref",
            actor_user_id=new_uuid())
        second = PrintProductionLabelUseCase().execute(
            conn, packaging_execution_id=packaging_id, operation_id=op_id,
            label_template_id=new_uuid(), barcode="1", qr_traceability_reference="ref",
            actor_user_id=new_uuid())
        assert second.entity_id == first.entity_id
        assert second.data["already_processed"] is True

    def test_print_unknown_packaging_fails(self, conn):
        result = PrintProductionLabelUseCase().execute(
            conn, packaging_execution_id=new_uuid(), operation_id=new_uuid(),
            label_template_id=new_uuid(), barcode="1", qr_traceability_reference="ref",
            actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "PACKAGING_NOT_FOUND"

    def test_reprint_increments_count_and_keeps_original_print_time(
            self, conn, approved_order_id):
        packaging_id = _package(conn, approved_order_id).entity_id
        printed = PrintProductionLabelUseCase().execute(
            conn, packaging_execution_id=packaging_id, operation_id=new_uuid(),
            label_template_id=new_uuid(), barcode="1", qr_traceability_reference="ref",
            actor_user_id=new_uuid())
        with MeatProcessingUnitOfWork(conn) as uow:
            original_printed_at = uow.production_labels.get(printed.entity_id).printed_at

        reprinted = ReprintProductionLabelUseCase().execute(
            conn, label_id=printed.entity_id, operation_id=new_uuid(), actor_user_id=new_uuid())
        assert reprinted.success
        assert reprinted.data["reprint_count"] == 1
        with MeatProcessingUnitOfWork(conn) as uow:
            label = uow.production_labels.get(printed.entity_id)
            assert label.printed_at == original_printed_at
            assert label.reprint_count == 1

    def test_reprint_unknown_label_fails(self, conn):
        result = ReprintProductionLabelUseCase().execute(
            conn, label_id=new_uuid(), operation_id=new_uuid(), actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "LABEL_NOT_FOUND"
