"""SQLite persistence for the canonical LOSS-15 investigation workflow."""

import json
from contextlib import contextmanager
from datetime import datetime, timezone

from backend.domain.losses.exceptions import LossStateTransitionError
from backend.shared.ids import new_uuid


class LossInvestigationRepository:
    def __init__(self, connection): self._db = connection

    @contextmanager
    def transaction(self):
        self._db.execute("SAVEPOINT loss15_investigation")
        try:
            yield
            self._db.execute("RELEASE SAVEPOINT loss15_investigation")
        except Exception:
            self._db.execute("ROLLBACK TO SAVEPOINT loss15_investigation")
            self._db.execute("RELEASE SAVEPOINT loss15_investigation")
            raise

    def find_processed(self, operation_id):
        row = self._db.execute("SELECT result_json FROM loss_processed_operations WHERE operation_id=?", (operation_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def get_case(self, case_id):
        row = self._db.execute("SELECT id,branch_id,warehouse_id,status FROM loss_cases WHERE id=?", (case_id,)).fetchone()
        return dict(zip(("id","branch_id","warehouse_id","status"), row)) if row else None

    def get_investigation(self, investigation_id):
        row = self._db.execute(
            "SELECT i.id,i.loss_case_id,c.branch_id,c.warehouse_id,i.status,i.opened_by_user_id,"
            "i.assigned_to_user_id,(SELECT COUNT(*) FROM loss_investigation_findings f WHERE f.investigation_id=i.id) "
            "FROM loss_investigations i JOIN loss_cases c ON c.id=i.loss_case_id WHERE i.id=?",
            (investigation_id,)).fetchone()
        return dict(zip(("id","loss_case_id","branch_id","warehouse_id","status",
            "opened_by_user_id","assigned_to_user_id","finding_count"), row)) if row else None

    def save_open(self, *, investigation_id, operation_id, case, assigned_to_user_id,
                  due_at, reason, actor_user_id, event):
        self._db.execute(
            "INSERT INTO loss_investigations (id,loss_case_id,operation_id,status,opened_by_user_id,assigned_to_user_id,opening_reason,opened_at,due_at) VALUES (?,?,?,'OPEN',?,?,?,?,?)",
            (investigation_id,case["id"],operation_id,actor_user_id,assigned_to_user_id,
             reason,self._now(),due_at))
        self._finish(operation_id, "OPEN_LOSS_INVESTIGATION", investigation_id,
                     "OPEN", case["id"], event)

    def save_evidence(self, *, investigation_id, operation_id, evidence,
                      actor_user_id, event, case):
        self._insert_evidence(investigation_id, case["loss_case_id"], evidence,
                              actor_user_id, "INVESTIGATION")
        self._mark_in_progress(investigation_id)
        self._finish(operation_id, "ADD_INVESTIGATION_EVIDENCE", investigation_id,
                     "IN_PROGRESS", case["loss_case_id"], event)

    def save_finding(self, *, finding_id, investigation_id, operation_id, cause_code,
                     description, is_primary, evidence, actor_user_id, event, case):
        now = self._now()
        if is_primary:
            self._db.execute("UPDATE loss_investigation_findings SET is_primary=0 WHERE investigation_id=?", (investigation_id,))
        self._db.execute(
            "INSERT INTO loss_investigation_findings (id,investigation_id,operation_id,cause_code,description,is_primary,recorded_by_user_id,recorded_at) VALUES (?,?,?,?,?,?,?,?)",
            (finding_id,investigation_id,operation_id,cause_code,description,int(is_primary),actor_user_id,now))
        self._insert_evidence(investigation_id, case["loss_case_id"], evidence,
                              actor_user_id, "FINDING", finding_id)
        self._mark_in_progress(investigation_id)
        self._finish(operation_id, "ADD_INVESTIGATION_FINDING", finding_id,
                     "RECORDED", case["loss_case_id"], event)

    def conclude(self, *, investigation_id, operation_id, conclusion, evidence,
                 actor_user_id, event, case):
        now = self._now()
        changed = self._db.execute(
            "UPDATE loss_investigations SET status='CONCLUDED',conclusion_operation_id=?,conclusion=?,concluded_by_user_id=?,concluded_at=? WHERE id=? AND status IN ('OPEN','IN_PROGRESS') AND opened_by_user_id<>? AND EXISTS (SELECT 1 FROM loss_investigation_findings WHERE investigation_id=?)",
            (operation_id,conclusion,actor_user_id,now,investigation_id,actor_user_id,
             investigation_id)).rowcount
        if changed != 1: raise LossStateTransitionError("La investigación cambió durante su conclusión")
        self._insert_evidence(investigation_id, case["loss_case_id"], evidence,
                              actor_user_id, "CONCLUSION")
        self._finish(operation_id, "CONCLUDE_LOSS_INVESTIGATION", investigation_id,
                     "CONCLUDED", case["loss_case_id"], event)

    def _insert_evidence(self, investigation_id, case_id, items, actor, phase, finding_id=None):
        for item in items:
            evidence_id = new_uuid()
            self._db.execute(
                "INSERT INTO loss_evidence (id,loss_case_id,evidence_type,storage_uri,checksum,captured_by_user_id,captured_at,metadata_json) VALUES (?,?,?,?,?,?,?,?)",
                (evidence_id,case_id,item.evidence_type.strip(),item.storage_uri.strip(),
                 item.checksum.strip().lower(),actor,self._now(),item.metadata_json))
            self._db.execute(
                "INSERT INTO loss_investigation_evidence (investigation_id,evidence_id,finding_id,phase) VALUES (?,?,?,?)",
                (investigation_id,evidence_id,finding_id,phase))

    def _mark_in_progress(self, investigation_id):
        changed = self._db.execute("UPDATE loss_investigations SET status='IN_PROGRESS' WHERE id=? AND status IN ('OPEN','IN_PROGRESS')", (investigation_id,)).rowcount
        if changed != 1: raise LossStateTransitionError("La investigación ya no está activa")

    def _finish(self, operation_id, operation_type, entity_id, status, case_id, event):
        now = self._now(); result = {"entity_id": entity_id, "status": status}
        self._db.execute("INSERT INTO loss_outbox (id,event_id,event_name,aggregate_id,operation_id,correlation_id,payload_json,created_at) VALUES (?,?,?,?,?,?,?,?)", (new_uuid(),event["event_id"],event["event_name"],case_id,operation_id,event["event_id"],json.dumps(event,sort_keys=True),now))
        self._db.execute("INSERT INTO loss_processed_operations (operation_id,operation_type,result_entity_id,result_json,processed_at) VALUES (?,?,?,?,?)", (operation_id,operation_type,entity_id,json.dumps(result,sort_keys=True),now))

    @staticmethod
    def _now(): return datetime.now(timezone.utc).isoformat()
