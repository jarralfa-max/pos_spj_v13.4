import importlib,sqlite3,unittest
from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.root_cause import LossRootCauseService,RecordRootCauseAnalysisCommand,RootCauseInput
from backend.domain.losses.root_cause import RootCauseMethod
from backend.infrastructure.persistence.loss_root_cause_repository import LossRootCauseRepository
from backend.shared.ids import new_uuid

class Authorization:
    def require(self,_actor,_permission): pass

class RootCausePersistenceTest(unittest.TestCase):
    def test_catalog_and_analysis_persist_atomically(self):
        db=sqlite3.connect(":memory:"); db.execute("PRAGMA foreign_keys=ON")
        importlib.import_module("migrations.standalone.174_losses_bounded_context_schema").run(db)
        branch,warehouse,actor,case_id,investigation_id=(new_uuid() for _ in range(5))
        classification_id,reason_id=db.execute("SELECT classification_id,id FROM loss_reasons LIMIT 1").fetchone()
        now="2026-08-03T10:00:00+00:00"
        db.execute("INSERT INTO loss_cases (id,operation_id,branch_id,warehouse_id,reported_by_user_id,classification_id,reason_id,origin,status,requires_inventory_posting,occurred_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",(case_id,new_uuid(),branch,warehouse,actor,classification_id,reason_id,"INVENTORY","UNDER_REVIEW",0,now,now,now))
        db.execute("INSERT INTO loss_investigations (id,loss_case_id,operation_id,status,opened_by_user_id,assigned_to_user_id,opening_reason,opened_at,due_at) VALUES (?,?,?,'IN_PROGRESS',?,?,?,?,?)",(investigation_id,case_id,new_uuid(),actor,new_uuid(),"Investigar",now,"2099-01-01T00:00:00+00:00"))
        catalog=[row[0] for row in db.execute("SELECT id FROM loss_root_cause_catalog ORDER BY code LIMIT 2")]
        service=LossRootCauseService(LossRootCauseRepository(db),Authorization())
        result=service.record(RecordRootCauseAnalysisCommand(new_uuid(),investigation_id,
            LossExecutionContext(actor,branch,frozenset(),frozenset({warehouse})),
            RootCauseMethod.FISHBONE,"Análisis Ishikawa",RootCauseInput(catalog[0],"Principal"),
            (RootCauseInput(catalog[1],"Contribuyente"),)))
        self.assertEqual(result.status,"RECORDED")
        self.assertEqual(db.execute("SELECT COUNT(*) FROM loss_root_causes").fetchone()[0],2)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM loss_root_causes WHERE role='PRIMARY'").fetchone()[0],1)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM loss_outbox").fetchone()[0],1)
        db.close()

if __name__=="__main__": unittest.main()
