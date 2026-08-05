import unittest
from contextlib import nullcontext
from datetime import datetime, timezone

from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.investigation import (
    AddInvestigationEvidenceCommand, AddInvestigationFindingCommand,
    ConcludeInvestigationCommand, InvestigationEvidenceInput,
    LossInvestigationService, OpenInvestigationCommand,
)
from backend.domain.losses.exceptions import LossInvariantError
from backend.shared.ids import new_uuid


class Authorization:
    def require(self, _actor, _permission): pass


class Repository:
    def __init__(self, ids):
        self.ids, self.processed, self.investigations, self.findings = ids, {}, {}, []
        self.case = {"id": ids["case"], "branch_id": ids["branch"],
                     "warehouse_id": ids["warehouse"], "status": "UNDER_REVIEW"}
    def transaction(self): return nullcontext()
    def find_processed(self, op): return self.processed.get(op)
    def get_case(self, case_id): return self.case if case_id == self.ids["case"] else None
    def get_investigation(self, investigation_id): return self.investigations.get(investigation_id)
    def save_open(self, **kw):
        self.investigations[kw["investigation_id"]] = {
            "id": kw["investigation_id"], "loss_case_id": kw["case"]["id"],
            "branch_id": kw["case"]["branch_id"], "warehouse_id": kw["case"]["warehouse_id"],
            "status": "OPEN", "opened_by_user_id": kw["actor_user_id"], "finding_count": 0}
        self.processed[kw["operation_id"]] = {"entity_id": kw["investigation_id"], "status": "OPEN"}
    def save_evidence(self, **kw):
        self.processed[kw["operation_id"]] = {"entity_id": kw["investigation_id"], "status": "IN_PROGRESS"}
        self.investigations[kw["investigation_id"]]["status"] = "IN_PROGRESS"
    def save_finding(self, **kw):
        item = self.investigations[kw["investigation_id"]]
        item["finding_count"] += 1; item["status"] = "IN_PROGRESS"
        self.processed[kw["operation_id"]] = {"entity_id": kw["finding_id"], "status": "RECORDED"}
    def conclude(self, **kw):
        self.investigations[kw["investigation_id"]]["status"] = "CONCLUDED"
        self.processed[kw["operation_id"]] = {"entity_id": kw["investigation_id"], "status": "CONCLUDED"}


def make_ids():
    return {name: new_uuid() for name in ("case", "branch", "warehouse", "opener",
        "investigator", "concluder", "open_op", "evidence_op", "finding_op", "conclude_op")}


def context(ids, actor):
    return LossExecutionContext(ids[actor], ids["branch"], frozenset(), frozenset({ids["warehouse"]}))


def evidence():
    return InvestigationEvidenceInput("PHOTO", "evidence://investigation/1", "c" * 64, "{}")


class InvestigationWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.ids = make_ids(); self.repo = Repository(self.ids)
        self.service = LossInvestigationService(self.repo, Authorization())

    def open(self):
        return self.service.open(OpenInvestigationCommand(self.ids["open_op"], self.ids["case"],
            context(self.ids, "opener"), self.ids["investigator"],
            datetime(2099, 8, 10, tzinfo=timezone.utc), "Investigar variación"))

    def test_open_evidence_finding_and_independent_conclusion(self):
        opened = self.open()
        self.service.add_evidence(AddInvestigationEvidenceCommand(self.ids["evidence_op"],
            opened.entity_id, context(self.ids, "investigator"), (evidence(),)))
        finding = self.service.add_finding(AddInvestigationFindingCommand(self.ids["finding_op"],
            opened.entity_id, context(self.ids, "investigator"), "PROCESS_FAILURE",
            "Temperatura fuera de rango", True, (evidence(),)))
        self.assertEqual(finding.status, "RECORDED")
        with self.assertRaises(LossInvariantError):
            self.service.conclude(ConcludeInvestigationCommand(self.ids["conclude_op"],
                opened.entity_id, context(self.ids, "opener"), "Causa confirmada", (evidence(),)))
        result = self.service.conclude(ConcludeInvestigationCommand(self.ids["conclude_op"],
            opened.entity_id, context(self.ids, "concluder"), "Causa confirmada", (evidence(),)))
        self.assertEqual(result.status, "CONCLUDED")

    def test_conclusion_requires_findings_and_evidence(self):
        opened = self.open()
        with self.assertRaises(LossInvariantError):
            self.service.conclude(ConcludeInvestigationCommand(self.ids["conclude_op"],
                opened.entity_id, context(self.ids, "concluder"), "Sin hallazgos", (evidence(),)))

    def test_open_is_idempotent_and_due_date_must_be_utc(self):
        first = self.open(); replay = self.open()
        self.assertEqual(first.entity_id, replay.entity_id); self.assertTrue(replay.replayed)
        with self.assertRaises(LossInvariantError):
            self.service.open(OpenInvestigationCommand(new_uuid(), self.ids["case"],
                context(self.ids, "opener"), self.ids["investigator"],
                datetime(2099, 8, 10), "Fecha ingenua"))


if __name__ == "__main__": unittest.main()
