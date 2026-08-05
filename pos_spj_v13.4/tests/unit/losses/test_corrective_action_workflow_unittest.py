import unittest
from contextlib import nullcontext
from datetime import datetime,timezone
from backend.application.losses.corrective_action import (CreateCorrectiveActionCommand,
    LossCorrectiveActionService,SubmitCorrectiveActionCommand,VerifyCorrectiveActionCommand)
from backend.application.losses.execution_context import LossExecutionContext
from backend.domain.losses.corrective_action import EffectivenessDecision
from backend.domain.losses.corrective_action import CorrectiveActionPolicy
from backend.domain.losses.exceptions import LossInvariantError
from backend.shared.ids import new_uuid

class Auth:
    def require(self,*_): pass
class Repo:
    def __init__(self,ids): self.ids=ids; self.items={}; self.processed={}
    def transaction(self): return nullcontext()
    def find_processed(self,op): return self.processed.get(op)
    def get_investigation(self,value): return {"id":value,"loss_case_id":self.ids["case"],"branch_id":self.ids["branch"],"warehouse_id":self.ids["warehouse"],"status":"CONCLUDED"}
    def get_action(self,value): return self.items.get(value)
    def save_created(self,**kw):
        self.items[kw["action_id"]]={"id":kw["action_id"],"investigation_id":kw["investigation"]["id"],"loss_case_id":kw["investigation"]["loss_case_id"],"branch_id":kw["investigation"]["branch_id"],"warehouse_id":kw["investigation"]["warehouse_id"],"status":"OPEN","created_by_user_id":kw["actor_user_id"],"owner_user_id":kw["owner_user_id"]}
        self.processed[kw["operation_id"]]={"entity_id":kw["action_id"],"status":"OPEN"}
    def submit(self,**kw): self.items[kw["action_id"]]["status"]="PENDING_VERIFICATION"; self.processed[kw["operation_id"]]={"entity_id":kw["action_id"],"status":"PENDING_VERIFICATION"}
    def verify(self,**kw): self.items[kw["action_id"]]["status"]=kw["decision"].value; self.processed[kw["operation_id"]]={"entity_id":kw["action_id"],"status":kw["decision"].value}
def ctx(ids,name): return LossExecutionContext(ids[name],ids["branch"],frozenset(),frozenset({ids["warehouse"]}))

class CorrectiveActionTest(unittest.TestCase):
    def setUp(self):
        self.ids={n:new_uuid() for n in ("case","branch","warehouse","investigation","creator","owner","verifier","create_op","submit_op","verify_op")}
        self.repo=Repo(self.ids); self.svc=LossCorrectiveActionService(self.repo,Auth())
    def create(self): return self.svc.create(CreateCorrectiveActionCommand(self.ids["create_op"],self.ids["investigation"],ctx(self.ids,"creator"),"Corregir proceso","Actualizar y capacitar",self.ids["owner"],datetime(2099,1,1,tzinfo=timezone.utc)))
    def test_create_assign_submit_and_verify_effectiveness(self):
        action=self.create()
        with self.assertRaises(LossInvariantError): self.svc.submit(SubmitCorrectiveActionCommand(self.ids["submit_op"],action.entity_id,ctx(self.ids,"creator"),"Ejecutada","evidence://action/1","a"*64))
        self.svc.submit(SubmitCorrectiveActionCommand(self.ids["submit_op"],action.entity_id,ctx(self.ids,"owner"),"Ejecutada","evidence://action/1","a"*64))
        result=self.svc.verify(VerifyCorrectiveActionCommand(self.ids["verify_op"],action.entity_id,ctx(self.ids,"verifier"),EffectivenessDecision.EFFECTIVE,"Resultado confirmado"))
        self.assertEqual(result.status,"EFFECTIVE")
    def test_owner_cannot_verify_and_due_date_requires_timezone(self):
        action=self.create(); self.svc.submit(SubmitCorrectiveActionCommand(self.ids["submit_op"],action.entity_id,ctx(self.ids,"owner"),"Lista","evidence://action/1","a"*64))
        with self.assertRaises(LossInvariantError): self.svc.verify(VerifyCorrectiveActionCommand(self.ids["verify_op"],action.entity_id,ctx(self.ids,"owner"),EffectivenessDecision.EFFECTIVE,"Auto verificación"))
        with self.assertRaises(LossInvariantError): self.svc.create(CreateCorrectiveActionCommand(new_uuid(),self.ids["investigation"],ctx(self.ids,"creator"),"Título","Detalle",self.ids["owner"],datetime(2099,1,1)))
    def test_create_is_idempotent(self):
        first=self.create(); replay=self.create(); self.assertEqual(first.entity_id,replay.entity_id); self.assertTrue(replay.replayed)
    def test_overdue_excludes_terminal_effectiveness_states(self):
        due=datetime(2026,1,1,tzinfo=timezone.utc); now=datetime(2026,2,1,tzinfo=timezone.utc)
        self.assertTrue(CorrectiveActionPolicy.is_overdue(due_at=due,status="OPEN",as_of=now))
        self.assertFalse(CorrectiveActionPolicy.is_overdue(due_at=due,status="EFFECTIVE",as_of=now))
if __name__=="__main__": unittest.main()
