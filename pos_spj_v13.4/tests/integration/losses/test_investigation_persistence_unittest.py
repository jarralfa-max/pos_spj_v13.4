import importlib
import sqlite3
import unittest
from datetime import datetime, timezone

from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.investigation import (
    AddInvestigationEvidenceCommand, AddInvestigationFindingCommand,
    ConcludeInvestigationCommand, InvestigationEvidenceInput,
    LossInvestigationService, OpenInvestigationCommand,
)
from backend.infrastructure.persistence.loss_investigation_repository import LossInvestigationRepository
from backend.shared.ids import new_uuid


class Authorization:
    def require(self, _actor, _permission): pass


class InvestigationPersistenceTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("PRAGMA foreign_keys=ON")
        importlib.import_module("migrations.standalone.174_losses_bounded_context_schema").run(self.db)
        self.branch, self.warehouse = new_uuid(), new_uuid()
        self.opener, self.assignee, self.concluder = new_uuid(), new_uuid(), new_uuid()
        self.case_id = new_uuid()
        classification_id, reason_id = self.db.execute(
            "SELECT classification_id,id FROM loss_reasons ORDER BY created_at,id LIMIT 1").fetchone()
        now = "2026-08-03T10:00:00+00:00"
        self.db.execute(
            "INSERT INTO loss_cases (id,operation_id,branch_id,warehouse_id,reported_by_user_id,classification_id,reason_id,origin,status,requires_inventory_posting,occurred_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.case_id,new_uuid(),self.branch,self.warehouse,self.opener,
             classification_id,reason_id,"INVENTORY","UNDER_REVIEW",0,now,now,now))
        self.service = LossInvestigationService(LossInvestigationRepository(self.db), Authorization())

    def tearDown(self): self.db.close()

    def context(self, actor):
        return LossExecutionContext(actor,self.branch,frozenset(),frozenset({self.warehouse}))

    @staticmethod
    def evidence(uri):
        return (InvestigationEvidenceInput("PHOTO",uri,"d" * 64,"{}"),)

    def test_complete_workflow_is_atomic_and_auditable(self):
        opened = self.service.open(OpenInvestigationCommand(new_uuid(),self.case_id,
            self.context(self.opener),self.assignee,
            datetime(2099,1,1,tzinfo=timezone.utc),"Variación crítica"))
        self.service.add_evidence(AddInvestigationEvidenceCommand(new_uuid(),opened.entity_id,
            self.context(self.assignee),self.evidence("evidence://investigation/general")))
        self.service.add_finding(AddInvestigationFindingCommand(new_uuid(),opened.entity_id,
            self.context(self.assignee),"PROCESS_FAILURE","Falla del proceso",True,
            self.evidence("evidence://investigation/finding")))
        result = self.service.conclude(ConcludeInvestigationCommand(new_uuid(),opened.entity_id,
            self.context(self.concluder),"Causa raíz confirmada",
            self.evidence("evidence://investigation/conclusion")))
        self.assertEqual(result.status,"CONCLUDED")
        self.assertEqual(self.db.execute("SELECT status FROM loss_investigations").fetchone()[0],"CONCLUDED")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM loss_investigation_findings").fetchone()[0],1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM loss_investigation_evidence").fetchone()[0],3)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM loss_outbox").fetchone()[0],4)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM loss_processed_operations").fetchone()[0],4)


if __name__ == "__main__": unittest.main()
