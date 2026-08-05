import unittest
from contextlib import nullcontext
from decimal import Decimal

from backend.application.losses.disposition import (
    AuthorizeDispositionCommand, CompleteDispositionCommand, DispositionEvidenceInput,
    LossDispositionService, PlanDispositionCommand,
)
from backend.application.losses.execution_context import LossExecutionContext
from backend.domain.losses.disposition import DispositionMethod
from backend.domain.losses.exceptions import LossInvariantError
from backend.shared.ids import new_uuid


class Authorization:
    def require(self, _actor, _permission): pass


class Result:
    success = True; message = "ok"
    def __init__(self, entity_id): self.entity_id = entity_id


class Inventory:
    def __init__(self): self.calls = []
    def dispose_quarantine(self, **kw):
        self.calls.append(kw); return Result(kw["quarantine_id"])


class Repository:
    def __init__(self, ids):
        self.ids, self.processed, self.items = ids, {}, {}
        self.case = {"id": ids["case"], "branch_id": ids["branch"],
            "warehouse_id": ids["warehouse"], "status": "TREATMENT_PENDING",
            "quarantine_id": ids["quarantine"], "quarantine_quantity": Decimal("3"),
            "quarantine_weight": Decimal("12")}
    def transaction(self): return nullcontext()
    def find_processed(self, op): return self.processed.get(op)
    def get_case(self, case_id): return self.case if case_id == self.ids["case"] else None
    def save_plan(self, **kw):
        self.items[kw["disposition_id"]] = {**kw, "loss_case_id": kw["case"]["id"],
            "status": "PLANNED", "planned_by_user_id": kw["actor_user_id"],
            "reason": kw["plan"].reason,
            "certificate_required": kw["plan"].certificate_required}
        self.processed[kw["operation_id"]] = {"entity_id": kw["disposition_id"], "status": "PLANNED"}
    def get_disposition(self, disposition_id): return self.items.get(disposition_id)
    def authorize(self, **kw):
        item = self.items[kw["disposition_id"]]; item.update(status="AUTHORIZED",
            authorized_by_user_id=kw["actor_user_id"])
        self.processed[kw["operation_id"]] = {"entity_id": kw["disposition_id"], "status": "AUTHORIZED"}
    def complete(self, **kw):
        self.items[kw["disposition_id"]]["status"] = "COMPLETED"
        self.processed[kw["operation_id"]] = {"entity_id": kw["disposition_id"], "status": "COMPLETED"}


def ids():
    return {name: new_uuid() for name in ("case", "branch", "warehouse", "quarantine",
        "planner", "authorizer", "operator", "plan_op", "auth_op", "complete_op")}


def context(ids, actor):
    return LossExecutionContext(ids[actor], ids["branch"], frozenset(),
                                frozenset({ids["warehouse"]}))


def evidence(kind="PHOTO"):
    return (DispositionEvidenceInput(kind, "evidence://disposition/1", "b" * 64),)


class DispositionWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.ids = ids(); self.repo = Repository(self.ids); self.inventory = Inventory()
        self.service = LossDispositionService(self.repo, self.inventory, Authorization())

    def plan(self, method=DispositionMethod.AUTHORIZED_DESTRUCTION):
        return self.service.plan(PlanDispositionCommand(self.ids["plan_op"], self.ids["case"],
            context(self.ids, "planner"), method, Decimal("3"), Decimal("12"),
            "Material no recuperable", evidence()))

    def test_double_confirmation_precedes_inventory_disposal(self):
        planned = self.plan(); self.assertEqual(self.inventory.calls, [])
        with self.assertRaises(LossInvariantError):
            self.service.authorize(AuthorizeDispositionCommand(self.ids["auth_op"],
                planned.disposition_id, context(self.ids, "planner"), "Autorizo"))
        self.service.authorize(AuthorizeDispositionCommand(self.ids["auth_op"],
            planned.disposition_id, context(self.ids, "authorizer"), "Autorizo"))
        self.assertEqual(self.inventory.calls, [])
        with self.assertRaises(LossInvariantError):
            self.service.complete(CompleteDispositionCommand(self.ids["complete_op"],
                planned.disposition_id, context(self.ids, "authorizer"), "CERT-1", evidence("CERTIFICATE")))
        completed = self.service.complete(CompleteDispositionCommand(self.ids["complete_op"],
            planned.disposition_id, context(self.ids, "operator"), "CERT-1", evidence("CERTIFICATE")))
        self.assertEqual(completed.status, "COMPLETED")
        self.assertEqual(len(self.inventory.calls), 1)
        self.assertFalse(self.inventory.calls[0]["owns_transaction"])

    def test_regulated_method_requires_certificate_and_completion_evidence(self):
        disposition_id = self.plan().disposition_id
        self.service.authorize(AuthorizeDispositionCommand(self.ids["auth_op"], disposition_id,
            context(self.ids, "authorizer"), "Autorizo"))
        with self.assertRaises(LossInvariantError):
            self.service.complete(CompleteDispositionCommand(self.ids["complete_op"], disposition_id,
                context(self.ids, "operator"), "", evidence("CERTIFICATE")))

    def test_plan_must_match_the_entire_quarantine_and_have_evidence(self):
        with self.assertRaises(LossInvariantError):
            self.service.plan(PlanDispositionCommand(self.ids["plan_op"], self.ids["case"],
                context(self.ids, "planner"), DispositionMethod.COMPOSTING,
                Decimal("1"), Decimal("12"), "Parcial", evidence()))
        with self.assertRaises(LossInvariantError):
            self.service.plan(PlanDispositionCommand(self.ids["plan_op"], self.ids["case"],
                context(self.ids, "planner"), DispositionMethod.COMPOSTING,
                Decimal("3"), Decimal("12"), "Sin evidencia", ()))

    def test_operations_are_idempotent(self):
        first = self.plan(); replay = self.plan()
        self.assertEqual(first.disposition_id, replay.disposition_id)
        self.assertTrue(replay.replayed)


if __name__ == "__main__": unittest.main()
