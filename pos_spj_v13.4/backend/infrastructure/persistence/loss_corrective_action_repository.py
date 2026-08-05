"""SQLite persistence for the LOSS-17 corrective-action workflow."""
import json
from contextlib import contextmanager
from datetime import datetime,timezone
from backend.domain.losses.exceptions import LossStateTransitionError
from backend.shared.ids import new_uuid
class LossCorrectiveActionRepository:
    def __init__(self,connection): self._db=connection
    @contextmanager
    def transaction(self):
        self._db.execute("SAVEPOINT loss17_corrective")
        try: yield; self._db.execute("RELEASE SAVEPOINT loss17_corrective")
        except Exception:
            self._db.execute("ROLLBACK TO SAVEPOINT loss17_corrective"); self._db.execute("RELEASE SAVEPOINT loss17_corrective"); raise
    def find_processed(self,operation_id):
        row=self._db.execute("SELECT result_json FROM loss_processed_operations WHERE operation_id=?",(operation_id,)).fetchone(); return json.loads(row[0]) if row else None
    def get_investigation(self,value):
        row=self._db.execute("SELECT i.id,i.loss_case_id,c.branch_id,c.warehouse_id,i.status FROM loss_investigations i JOIN loss_cases c ON c.id=i.loss_case_id WHERE i.id=?",(value,)).fetchone(); return dict(zip(("id","loss_case_id","branch_id","warehouse_id","status"),row)) if row else None
    def get_action(self,value):
        row=self._db.execute("SELECT a.id,a.investigation_id,i.loss_case_id,c.branch_id,c.warehouse_id,a.status,a.created_by_user_id,a.owner_user_id FROM loss_corrective_actions a JOIN loss_investigations i ON i.id=a.investigation_id JOIN loss_cases c ON c.id=i.loss_case_id WHERE a.id=?",(value,)).fetchone(); return dict(zip(("id","investigation_id","loss_case_id","branch_id","warehouse_id","status","created_by_user_id","owner_user_id"),row)) if row else None
    def save_created(self,*,action_id,operation_id,investigation,title,description,owner_user_id,due_at,actor_user_id,event):
        now=self._now(); self._db.execute("INSERT INTO loss_corrective_actions (id,investigation_id,operation_id,title,description,created_by_user_id,owner_user_id,status,due_at,created_at) VALUES (?,?,?,?,?,?,?,'OPEN',?,?)",(action_id,investigation["id"],operation_id,title,description,actor_user_id,owner_user_id,due_at,now)); self._finish(operation_id,"CREATE_CORRECTIVE_ACTION",action_id,"OPEN",investigation["loss_case_id"],event)
    def submit(self,*,action_id,operation_id,completion_notes,evidence_uri,checksum,actor_user_id,event,case):
        now=self._now(); changed=self._db.execute("UPDATE loss_corrective_actions SET status='PENDING_VERIFICATION',submission_operation_id=?,completion_notes=?,completion_evidence_uri=?,completion_evidence_checksum=?,submitted_at=? WHERE id=? AND status IN ('OPEN','IN_PROGRESS') AND owner_user_id=?",(operation_id,completion_notes,evidence_uri,checksum,now,action_id,actor_user_id)).rowcount
        if changed!=1: raise LossStateTransitionError("La acción cambió durante el envío")
        self._finish(operation_id,"SUBMIT_CORRECTIVE_ACTION",action_id,"PENDING_VERIFICATION",case["loss_case_id"],event)
    def verify(self,*,action_id,operation_id,decision,notes,actor_user_id,event,case):
        now=self._now(); changed=self._db.execute("UPDATE loss_corrective_actions SET status=?,verification_operation_id=?,verified_by_user_id=?,verified_at=?,effectiveness_notes=? WHERE id=? AND status='PENDING_VERIFICATION' AND owner_user_id<>? AND created_by_user_id<>?",(decision.value,operation_id,actor_user_id,now,notes,action_id,actor_user_id,actor_user_id)).rowcount
        if changed!=1: raise LossStateTransitionError("La acción cambió durante la verificación")
        self._finish(operation_id,"VERIFY_CORRECTIVE_ACTION",action_id,decision.value,case["loss_case_id"],event)
    def _finish(self,op,kind,entity,status,case_id,event):
        now=self._now(); result={"entity_id":entity,"status":status}; self._db.execute("INSERT INTO loss_outbox (id,event_id,event_name,aggregate_id,operation_id,correlation_id,payload_json,created_at) VALUES (?,?,?,?,?,?,?,?)",(new_uuid(),event["event_id"],event["event_name"],case_id,op,event["event_id"],json.dumps(event,sort_keys=True),now)); self._db.execute("INSERT INTO loss_processed_operations (operation_id,operation_type,result_entity_id,result_json,processed_at) VALUES (?,?,?,?,?)",(op,kind,entity,json.dumps(result,sort_keys=True),now))
    @staticmethod
    def _now(): return datetime.now(timezone.utc).isoformat()
