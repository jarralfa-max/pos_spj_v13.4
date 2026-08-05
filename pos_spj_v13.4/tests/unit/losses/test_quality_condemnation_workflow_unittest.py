import unittest
from contextlib import nullcontext
from decimal import Decimal

from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.quality_control import (
    QualityEvidenceInput, QualityInspectionCommand, QualityInspectionService,
)
from backend.domain.losses.exceptions import LossInvariantError
from backend.domain.losses.quality_control import ContaminationLevel, QualityDecision


class Authorization:
    def __init__(self): self.permissions = []
    def require(self, actor, permission): self.permissions.append((actor, permission))


class Repository:
    def __init__(self):
        self.processed = {}
        self.case = {"id": "case", "branch_id": "branch", "warehouse_id": "warehouse",
                     "status": "SUBMITTED", "classification": "CONTAMINATION",
                     "product_id": "product", "lot_id": "lot", "quantity": Decimal("2"),
                     "weight": Decimal("8.5"), "quarantine_id": None, "blocked_by_user_id": None}
    def transaction(self): return nullcontext()
    def find_processed(self, operation_id): return self.processed.get(operation_id)
    def get_quality_case(self, case_id, lot_id):
        return self.case if (case_id, lot_id) == ("case", "lot") else None
    def record_rejection(self, **kw):
        self.case.update(status="TREATMENT_PENDING", quarantine_id=kw["quarantine_id"],
                         blocked_by_user_id=kw["actor_user_id"])
        self.processed[kw["operation_id"]] = {"case_id": "case", "status": "REJECTED",
                                               "quarantine_id": kw["quarantine_id"]}
    def record_condemnation(self, **kw):
        self.processed[kw["operation_id"]] = {"case_id": "case", "status": "CONDEMNED_PENDING_DISPOSITION",
                                               "quarantine_id": self.case["quarantine_id"]}


class Result:
    success = True
    message = "ok"
    def __init__(self, entity_id, **data):
        self.entity_id = entity_id
        self.data = data


class Inventory:
    def __init__(self): self.calls = []
    def record_temperature(self, **kw):
        self.calls.append(("temperature", kw)); return Result("reading", status="OUT_OF_RANGE")
    def quarantine(self, **kw):
        self.calls.append(("quarantine", kw)); return Result("quarantine")


def context(actor="inspector"):
    return LossExecutionContext(actor, "branch", frozenset(), frozenset({"warehouse"}))


def evidence():
    return (QualityEvidenceInput("PHOTO", "evidence://photo/1", "a" * 64),)


class QualityWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.repo, self.inventory = Repository(), Inventory()
        self.service = QualityInspectionService(self.repo, self.inventory, Authorization())

    def test_rejection_records_temperature_then_quarantines_atomically(self):
        command = QualityInspectionCommand(
            "op-reject", "case", "lot", context(), QualityDecision.REJECT,
            ContaminationLevel.SUSPECTED, evidence(), "Empaque contaminado",
            sensor_id="sensor", temperature=Decimal("9.5"),
            minimum_temperature=Decimal("0"), maximum_temperature=Decimal("4"))
        result = self.service.inspect(command)
        replay = self.service.inspect(command)
        self.assertEqual([name for name, _ in self.inventory.calls], ["temperature", "quarantine"])
        self.assertEqual(result.status, "REJECTED")
        self.assertTrue(replay.replayed)
        self.assertFalse(self.inventory.calls[0][1]["owns_transaction"])

    def test_condemnation_requires_prior_block_and_different_actor(self):
        self.repo.case.update(status="TREATMENT_PENDING", quarantine_id="quarantine",
                              blocked_by_user_id="inspector")
        command = QualityInspectionCommand(
            "op-condemn", "case", "lot", context("inspector"), QualityDecision.CONDEMN,
            ContaminationLevel.CONFIRMED, evidence(), "Producto no inocuo")
        with self.assertRaises(LossInvariantError): self.service.inspect(command)
        result = self.service.inspect(QualityInspectionCommand(
            "op-condemn", "case", "lot", context("quality-manager"), QualityDecision.CONDEMN,
            ContaminationLevel.CONFIRMED, evidence(), "Producto no inocuo"))
        self.assertEqual(result.status, "CONDEMNED_PENDING_DISPOSITION")
        self.assertEqual(self.inventory.calls, [])

    def test_evidence_and_decimal_temperature_are_mandatory_quality_boundaries(self):
        with self.assertRaises(LossInvariantError):
            self.service.inspect(QualityInspectionCommand(
                "op-no-evidence", "case", "lot", context(), QualityDecision.REJECT,
                ContaminationLevel.NONE, (), "Sin evidencia"))
        with self.assertRaises(LossInvariantError):
            self.service.inspect(QualityInspectionCommand(
                "op-float", "case", "lot", context(), QualityDecision.REJECT,
                ContaminationLevel.NONE, evidence(), "Temperatura inválida",
                sensor_id="sensor", temperature=8.2,
                minimum_temperature=Decimal("0"), maximum_temperature=Decimal("4")))


if __name__ == "__main__": unittest.main()
