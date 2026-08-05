import unittest
from contextlib import nullcontext
from decimal import Decimal

from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.recovery import (
    ApproveRecoveryCommand, LossRecoveryService, RecordRecoveryCommand,
)
from backend.domain.losses.exceptions import LossInvariantError
from backend.domain.losses.recovery import RecoveryType
from backend.shared.ids import new_uuid


class Authorization:
    def require(self, _actor, _permission): pass


class Result:
    success = True; message = "ok"
    def __init__(self, entity_id): self.entity_id = entity_id


class Inventory:
    def __init__(self): self.calls = []
    def release_quarantine(self, **kw):
        self.calls.append(kw); return Result(kw["quarantine_id"])


class Repository:
    def __init__(self, ids):
        self.ids, self.processed, self.recoveries = ids, {}, {}
        self.case = {"id": ids["case"], "branch_id": ids["branch"],
            "warehouse_id": ids["warehouse"], "status": "TREATMENT_PENDING",
            "gross_value": Decimal("500"), "recovered_value": Decimal("50"),
            "quarantine_id": ids["quarantine"], "quarantine_quantity": Decimal("2"),
            "quarantine_weight": Decimal("10"), "loss_quantity": Decimal("2"),
            "loss_weight": Decimal("10"), "recovered_quantity": Decimal("0"),
            "recovered_weight": Decimal("0")}
    def transaction(self): return nullcontext()
    def find_processed(self, op): return self.processed.get(op)
    def get_case(self, case_id): return self.case if case_id == self.ids["case"] else None
    def validate_reference(self, recovery_type, reference_id, target_product_id):
        return self.ids["claim"] if recovery_type == "CLAIM" else self.ids["movement"]
    def save_pending(self, **kw):
        plan = kw["plan"]
        self.recoveries[kw["recovery_id"]] = {**kw, "status": "PENDING_APPROVAL",
            "loss_case_id": kw["case"]["id"], "recorded_by_user_id": kw["actor_user_id"],
            "recovery_type": plan.recovery_type.value, "quantity": plan.quantity,
            "weight": plan.weight, "recovered_value": plan.recovered_value}
        self.processed[kw["operation_id"]] = {"entity_id": kw["recovery_id"],
                                               "status": "PENDING_APPROVAL"}
    def get_recovery(self, recovery_id): return self.recoveries.get(recovery_id)
    def approve(self, **kw):
        recovery = self.recoveries[kw["recovery_id"]]; recovery["status"] = "APPROVED"
        self.case["recovered_value"] += recovery["recovered_value"]
        self.processed[kw["operation_id"]] = {"entity_id": kw["recovery_id"],
                                               "status": "APPROVED"}


def ids():
    return {name: new_uuid() for name in ("case", "branch", "warehouse", "actor",
        "approver", "quarantine", "movement", "claim", "product", "record_op", "approve_op")}


class LossRecoveryWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.ids = ids(); self.repo = Repository(self.ids); self.inventory = Inventory()
        self.service = LossRecoveryService(self.repo, self.inventory, Authorization())
        self.context = LossExecutionContext(self.ids["actor"], self.ids["branch"],
            frozenset(), frozenset({self.ids["warehouse"]}))
        self.approver = LossExecutionContext(self.ids["approver"], self.ids["branch"],
            frozenset(), frozenset({self.ids["warehouse"]}))

    def record(self, recovery_type=RecoveryType.REWORK, **overrides):
        values = dict(operation_id=self.ids["record_op"], loss_case_id=self.ids["case"],
            context=self.context, recovery_type=recovery_type, quantity=Decimal("2"),
            weight=Decimal("10"), recovered_value=Decimal("100"), reference_id=None,
            target_product_id=None, notes="Material recuperable")
        values.update(overrides)
        return self.service.record(RecordRecoveryCommand(**values))

    def test_rework_is_pending_until_independent_approval_then_releases_quarantine(self):
        pending = self.record(); replay = self.record()
        self.assertEqual(pending.status, "PENDING_APPROVAL"); self.assertTrue(replay.replayed)
        self.assertEqual(self.inventory.calls, [])
        with self.assertRaises(LossInvariantError):
            self.service.approve(ApproveRecoveryCommand(self.ids["approve_op"],
                pending.recovery_id, self.context, "Autorizo"))
        approved = self.service.approve(ApproveRecoveryCommand(self.ids["approve_op"],
            pending.recovery_id, self.approver, "Autorizo reproceso"))
        self.assertEqual(approved.status, "APPROVED")
        self.assertEqual(self.inventory.calls[0]["quarantine_id"], self.ids["quarantine"])

    def test_by_product_requires_target_and_posted_inventory_reference_without_release(self):
        pending = self.record(RecoveryType.BY_PRODUCT, reference_id=self.ids["movement"],
                              target_product_id=self.ids["product"])
        self.service.approve(ApproveRecoveryCommand(self.ids["approve_op"],
            pending.recovery_id, self.approver, "Salida productiva verificada"))
        self.assertEqual(self.inventory.calls, [])

    def test_paid_claim_is_financial_recovery_without_inventory_mutation(self):
        pending = self.record(RecoveryType.CLAIM, reference_id=self.ids["claim"],
                              quantity=Decimal("0"), weight=Decimal("0"))
        self.service.approve(ApproveRecoveryCommand(self.ids["approve_op"],
            pending.recovery_id, self.approver, "Pago confirmado"))
        self.assertEqual(self.inventory.calls, [])

    def test_recovered_value_cannot_exceed_remaining_loss(self):
        with self.assertRaises(LossInvariantError):
            self.record(recovered_value=Decimal("451"))


if __name__ == "__main__": unittest.main()
