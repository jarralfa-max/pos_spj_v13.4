import importlib
import sqlite3
import unittest
from decimal import Decimal

from backend.application.inventory.use_cases import PostInventoryMovementUseCase, ReverseInventoryMovementUseCase
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.loss_inventory_integration import LossInventoryIntegrationService, PostLossInventoryCommand, RequestLossInventoryCommand, ReverseLossInventoryCommand
from backend.domain.inventory.entities.inventory_movement import InventoryMovement, InventoryMovementLine
from backend.domain.inventory.enums import MovementType
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.integrations.losses_inventory_gateway import LossesInventoryGateway
from backend.infrastructure.persistence.loss_inventory_repository import LossInventoryRepository
from backend.shared.ids import new_uuid


class _Allow:
    def require(self, _actor, _permission): pass


class _FailAfterInventoryRepository(LossInventoryRepository):
    def record_posted(self, *_args, **_kwargs):
        raise RuntimeError("simulated loss state failure")


class LossInventoryFlowTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        create_inventory_schema(self.db)
        importlib.import_module("migrations.standalone.174_losses_bounded_context_schema").run(self.db)
        self.actor, self.branch, self.warehouse, self.product = (new_uuid() for _ in range(4))
        self.location = new_uuid()
        self.db.execute(
            "INSERT INTO storage_locations (id,warehouse_id,code,name,location_type,status) "
            "VALUES (?,?,?,?, 'AVAILABLE','ACTIVE')",
            (self.location, self.warehouse, "AVAILABLE", "Disponible"))
        self.context = LossExecutionContext(
            self.actor, self.branch, frozenset({self.branch}), frozenset({self.warehouse}),
            frozenset({InventoryPermissions.VIEW_OWN_BRANCH}))
        classification_id, reason_id = self.db.execute(
            "SELECT c.id,r.id FROM loss_classifications c JOIN loss_reasons r "
            "ON r.classification_id=c.id WHERE c.code='HANDLING_DAMAGE'").fetchone()
        self.case_id, case_operation, line_id = new_uuid(), new_uuid(), new_uuid()
        now = "2026-08-03T00:00:00+00:00"
        self.db.execute(
            "INSERT INTO loss_cases (id,operation_id,branch_id,warehouse_id,reported_by_user_id,"
            "classification_id,reason_id,origin,status,requires_inventory_posting,gross_value,"
            "recoverable_value,net_loss_value,occurred_at,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?, 'APPROVED',1,'0','0','0',?,?,?)",
            (self.case_id, case_operation, self.branch, self.warehouse, self.actor,
             classification_id, reason_id, "INVENTORY", now, now, now))
        self.db.execute(
            "INSERT INTO loss_lines (id,loss_case_id,product_id,quantity,weight,unit,unit_cost,"
            "gross_value,recoverable_value,net_loss_value,created_at) "
            "VALUES (?,?,?,'2.5','0','PZA','0','0','0','0',?)",
            (line_id, self.case_id, self.product, now))
        receipt = InventoryMovement.create(
            movement_type=MovementType.PURCHASE_RECEIPT, branch_id=self.branch,
            warehouse_id=self.warehouse, source_module="test",
            source_document_type="SEED", source_document_id=new_uuid(),
            operation_id=new_uuid(), created_by_user_id=self.actor,
            lines=[InventoryMovementLine.create(product_id=self.product,
                                                 quantity=Decimal("10"),
                                                 to_location_id=self.location)])
        self.assertTrue(PostInventoryMovementUseCase().execute(
            self.db, receipt, actor_user_id=self.actor).success)
        gateway = LossesInventoryGateway(
            self.db, PostInventoryMovementUseCase(), ReverseInventoryMovementUseCase())
        self.service = LossInventoryIntegrationService(
            LossInventoryRepository(self.db), gateway, _Allow())

    def tearDown(self):
        self.db.close()

    def test_request_post_replay_and_reverse_are_atomic(self):
        request_op, post_op, reverse_op = new_uuid(), new_uuid(), new_uuid()
        self.service.request(RequestLossInventoryCommand(request_op, self.case_id, self.context))
        posted = self.service.post(PostLossInventoryCommand(post_op, self.case_id, self.context))
        replay = self.service.post(PostLossInventoryCommand(post_op, self.case_id, self.context))
        self.assertTrue(replay.replayed)
        self.assertEqual("7.5", self._quantity())
        reversed_result = self.service.reverse(ReverseLossInventoryCommand(
            reverse_op, self.case_id, self.context, "Corrección de prueba"))
        self.assertEqual("REVERSED", reversed_result.status.value)
        self.assertEqual("10.0", self._quantity())
        self.assertEqual(3, self.db.execute(
            "SELECT COUNT(*) FROM loss_processed_operations").fetchone()[0])
        self.assertEqual(posted.inventory_movement_id, self.db.execute(
            "SELECT inventory_movement_id FROM loss_cases WHERE id=?", (self.case_id,)).fetchone()[0])

    def test_inventory_projection_rolls_back_when_loss_state_write_fails(self):
        self.service.request(RequestLossInventoryCommand(new_uuid(), self.case_id, self.context))
        failing = LossInventoryIntegrationService(
            _FailAfterInventoryRepository(self.db),
            LossesInventoryGateway(
                self.db, PostInventoryMovementUseCase(), ReverseInventoryMovementUseCase()),
            _Allow())
        operation_id = new_uuid()
        with self.assertRaises(RuntimeError):
            failing.post(PostLossInventoryCommand(operation_id, self.case_id, self.context))
        self.assertEqual("10", self._quantity())
        self.assertIsNone(self.db.execute(
            "SELECT id FROM inventory_ledger WHERE operation_id=?", (operation_id,)).fetchone())

    def _quantity(self):
        return self.db.execute(
            "SELECT quantity FROM inventory_balances WHERE product_id=? AND branch_id=? "
            "AND warehouse_id=?", (self.product, self.branch, self.warehouse)).fetchone()[0]


if __name__ == "__main__": unittest.main()
