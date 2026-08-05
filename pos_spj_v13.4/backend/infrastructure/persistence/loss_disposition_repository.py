"""SQLite adapter for the canonical LOSS-14 disposition workflow."""

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.losses.exceptions import LossStateTransitionError
from backend.shared.ids import new_uuid


class LossDispositionRepository:
    def __init__(self, connection): self._db = connection

    @contextmanager
    def transaction(self):
        self._db.execute("SAVEPOINT loss14_disposition")
        try:
            yield
            self._db.execute("RELEASE SAVEPOINT loss14_disposition")
        except Exception:
            self._db.execute("ROLLBACK TO SAVEPOINT loss14_disposition")
            self._db.execute("RELEASE SAVEPOINT loss14_disposition")
            raise

    def find_processed(self, operation_id):
        row = self._db.execute("SELECT result_json FROM loss_processed_operations WHERE operation_id=?", (operation_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def get_case(self, case_id):
        row = self._db.execute(
            "SELECT c.id,c.branch_id,c.warehouse_id,c.status,q.id,q.quantity,q.weight "
            "FROM loss_cases c LEFT JOIN inventory_quarantine q ON q.id=(SELECT iq.id "
            "FROM inventory_quarantine iq JOIN loss_lines ll ON ll.lot_id=iq.lot_id "
            "WHERE ll.loss_case_id=c.id AND iq.status IN ('OPEN','UNDER_REVIEW','PARTIALLY_RELEASED') "
            "ORDER BY iq.created_at DESC,iq.id DESC LIMIT 1) WHERE c.id=?", (case_id,)).fetchone()
        if not row: return None
        data = dict(zip(("id","branch_id","warehouse_id","status","quarantine_id","quarantine_quantity","quarantine_weight"), row))
        data["quarantine_quantity"] = Decimal(str(data["quarantine_quantity"] or "0"))
        data["quarantine_weight"] = Decimal(str(data["quarantine_weight"] or "0"))
        return data

    def save_plan(self, *, disposition_id, operation_id, case, plan, evidence, actor_user_id, event):
        self._db.execute(
            "INSERT INTO loss_dispositions (id,loss_case_id,quarantine_id,operation_id,method_code,status,quantity,weight,planned_by_user_id,reason,certificate_required,created_at) VALUES (?,?,?,?,?,'PLANNED',?,?,?,?,?,?)",
            (disposition_id,case["id"],case["quarantine_id"],operation_id,plan.method.value,str(plan.quantity),str(plan.weight),actor_user_id,plan.reason,int(plan.certificate_required),self._now()))
        self._evidence(disposition_id, case["id"], evidence, actor_user_id, "PLANNING")
        self._finish(operation_id, "PLAN_LOSS_DISPOSITION", disposition_id, "PLANNED", case["id"], event)

    def get_disposition(self, disposition_id):
        row = self._db.execute("SELECT id,loss_case_id,status,planned_by_user_id,authorized_by_user_id,reason,certificate_required FROM loss_dispositions WHERE id=?", (disposition_id,)).fetchone()
        return dict(zip(("id","loss_case_id","status","planned_by_user_id","authorized_by_user_id","reason","certificate_required"), row)) if row else None

    def authorize(self, *, disposition_id, operation_id, actor_user_id, reason, event):
        changed = self._db.execute("UPDATE loss_dispositions SET status='AUTHORIZED',authorization_operation_id=?,authorized_by_user_id=?,authorization_reason=?,authorized_at=? WHERE id=? AND status='PLANNED' AND planned_by_user_id<>?", (operation_id,actor_user_id,reason,self._now(),disposition_id,actor_user_id)).rowcount
        if changed != 1: raise LossStateTransitionError("La disposiciÃ³n cambiÃ³ durante la autorizaciÃ³n")
        self._finish(operation_id, "AUTHORIZE_LOSS_DISPOSITION", disposition_id, "AUTHORIZED", event["loss_case_id"], event)

    def complete(self, *, disposition_id, operation_id, actor_user_id, certificate_reference, evidence, event, case):
        now = self._now()
        changed = self._db.execute("UPDATE loss_dispositions SET status='COMPLETED',completion_operation_id=?,completed_by_user_id=?,completed_at=?,certificate_reference=? WHERE id=? AND status='AUTHORIZED' AND authorized_by_user_id<>?", (operation_id,actor_user_id,now,certificate_reference,disposition_id,actor_user_id)).rowcount
        if changed != 1: raise LossStateTransitionError("La disposiciÃ³n cambiÃ³ durante su ejecuciÃ³n")
        self._evidence(disposition_id, case["id"], evidence, actor_user_id, "COMPLETION")
        changed = self._db.execute("UPDATE loss_cases SET status='CLOSED',closed_at=?,updated_at=?,version=version+1 WHERE id=? AND status='TREATMENT_PENDING'", (now,now,case["id"])).rowcount
        if changed != 1: raise LossStateTransitionError("El expediente cambiÃ³ durante el cierre")
        self._finish(operation_id, "COMPLETE_LOSS_DISPOSITION", disposition_id, "COMPLETED", case["id"], event)

    def _evidence(self, disposition_id, case_id, evidence, actor, phase):
        for item in evidence:
            evidence_id = new_uuid()
            self._db.execute("INSERT INTO loss_evidence (id,loss_case_id,evidence_type,storage_uri,checksum,metadata_json,captured_by_user_id,captured_at) VALUES (?,?,?,?,?,?,?,?)", (evidence_id,case_id,item.evidence_type,item.storage_uri,item.checksum.lower(),item.metadata_json,actor,self._now()))
            self._db.execute("INSERT INTO loss_disposition_evidence (disposition_id,evidence_id,phase) VALUES (?,?,?)", (disposition_id,evidence_id,phase))

    def _finish(self, operation_id, operation_type, entity_id, status, case_id, event):
        now = self._now(); result = {"entity_id": entity_id, "status": status}
        self._db.execute("INSERT INTO loss_outbox (id,event_id,event_name,aggregate_id,operation_id,correlation_id,payload_json,created_at) VALUES (?,?,?,?,?,?,?,?)", (new_uuid(),event["event_id"],event["event_name"],case_id,operation_id,event["event_id"],json.dumps(event,sort_keys=True),now))
        self._db.execute("INSERT INTO loss_processed_operations (operation_id,operation_type,result_entity_id,result_json,processed_at) VALUES (?,?,?,?,?)", (operation_id,operation_type,entity_id,json.dumps(result,sort_keys=True),now))

    @staticmethod
    def _now(): return datetime.now(timezone.utc).isoformat()
