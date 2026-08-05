import importlib,sqlite3,unittest
from datetime import datetime,timezone
from backend.application.losses.corrective_action import CreateCorrectiveActionCommand,LossCorrectiveActionService,SubmitCorrectiveActionCommand,VerifyCorrectiveActionCommand
from backend.application.losses.execution_context import LossExecutionContext
from backend.domain.losses.corrective_action import EffectivenessDecision
from backend.infrastructure.persistence.loss_corrective_action_repository import LossCorrectiveActionRepository
from backend.shared.ids import new_uuid
class Auth:
    def require(self,*_): pass
class CorrectivePersistenceTest(unittest.TestCase):
    def test_full_effectiveness_workflow_is_atomic(self):
        db=sqlite3.connect(":memory:"); db.execute("PRAGMA foreign_keys=ON"); importlib.import_module("migrations.standalone.174_losses_bounded_context_schema").run(db)
        branch,warehouse,creator,owner,verifier,case_id,investigation=(new_uuid() for _ in range(7)); classification,reason=db.execute("SELECT classification_id,id FROM loss_reasons LIMIT 1").fetchone(); now="2026-08-03T10:00:00+00:00"
        db.execute("INSERT INTO loss_cases (id,operation_id,branch_id,warehouse_id,reported_by_user_id,classification_id,reason_id,origin,status,requires_inventory_posting,occurred_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",(case_id,new_uuid(),branch,warehouse,creator,classification,reason,"INVENTORY","CLOSED",0,now,now,now))
        db.execute("INSERT INTO loss_investigations (id,loss_case_id,operation_id,status,opened_by_user_id,assigned_to_user_id,opening_reason,opened_at,due_at,conclusion_operation_id,conclusion,concluded_by_user_id,concluded_at) VALUES (?,?,?,'CONCLUDED',?,?,?,?,?,?,?,?,?)",(investigation,case_id,new_uuid(),creator,owner,"Investigar",now,"2099-01-01T00:00:00+00:00",new_uuid(),"Concluida",verifier,now))
        svc=LossCorrectiveActionService(LossCorrectiveActionRepository(db),Auth()); context=lambda actor:LossExecutionContext(actor,branch,frozenset(),frozenset({warehouse}))
        action=svc.create(CreateCorrectiveActionCommand(new_uuid(),investigation,context(creator),"Corregir","Implementar control",owner,datetime(2099,2,1,tzinfo=timezone.utc)))
        svc.submit(SubmitCorrectiveActionCommand(new_uuid(),action.entity_id,context(owner),"Implementada","evidence://corrective/1","e"*64))
        result=svc.verify(VerifyCorrectiveActionCommand(new_uuid(),action.entity_id,context(verifier),EffectivenessDecision.EFFECTIVE,"Sin recurrencia"))
        self.assertEqual(result.status,"EFFECTIVE"); self.assertEqual(db.execute("SELECT status FROM loss_corrective_actions").fetchone()[0],"EFFECTIVE"); self.assertEqual(db.execute("SELECT COUNT(*) FROM loss_outbox").fetchone()[0],3); db.close()
if __name__=="__main__": unittest.main()
