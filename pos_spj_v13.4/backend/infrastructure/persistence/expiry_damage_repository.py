"""SQLite persistence for the LOSS-10 expiry/damage workflow."""

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.losses.events import build_loss_event
from backend.domain.losses.exceptions import LossInvariantError, LossStateTransitionError
from backend.shared.ids import new_uuid


class ExpiryDamageRepository:
    def __init__(self, connection) -> None:
        self._db = connection

    @contextmanager
    def transaction(self):
        self._db.execute("SAVEPOINT loss10_expiry_damage")
        try:
            yield
            self._db.execute("RELEASE SAVEPOINT loss10_expiry_damage")
        except Exception:
            self._db.execute("ROLLBACK TO SAVEPOINT loss10_expiry_damage")
            self._db.execute("RELEASE SAVEPOINT loss10_expiry_damage")
            raise

    def find_processed(self, operation_id):
        row = self._db.execute(
            "SELECT result_json FROM loss_processed_operations WHERE operation_id=?",
            (operation_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def get_lot_case(self, case_id, lot_id):
        row = self._db.execute(
            "SELECT lc.id,lc.branch_id,lc.warehouse_id,lc.status,ll.product_id,ll.lot_id,"
            "ll.quantity,ll.weight,il.expiration_date,ra.quarantine_id "
            "FROM loss_cases lc JOIN loss_lines ll ON ll.loss_case_id=lc.id "
            "JOIN inventory_lots il ON il.id=ll.lot_id "
            "LEFT JOIN loss_lot_risk_assessments ra ON ra.id=("
            "SELECT x.id FROM loss_lot_risk_assessments x WHERE x.loss_case_id=lc.id "
            "AND x.lot_id=ll.lot_id AND x.quarantine_id IS NOT NULL "
            "ORDER BY x.assessed_at DESC,x.id DESC LIMIT 1) "
            "WHERE lc.id=? AND ll.lot_id=? ORDER BY ll.created_at,ll.id LIMIT 1",
            (case_id, lot_id)).fetchone()
        if not row: return None
        keys = ("id", "branch_id", "warehouse_id", "status", "product_id", "lot_id",
                "quantity", "weight", "expiration_date", "quarantine_id")
        data = dict(zip(keys, row))
        data["quantity"] = Decimal(str(data["quantity"]))
        data["weight"] = Decimal(str(data["weight"]))
        return data

    def record_assessment(self, *, operation_id, assessment, case, actor_user_id):
        assessment_id = self._insert_assessment(operation_id, assessment, case, actor_user_id, None)
        self._processed(operation_id, "ASSESS_LOT_RISK", assessment_id,
                        {"kind": "ASSESS", "entity_id": case["id"],
                         "risk_level": assessment.risk_level.value})

    def record_block(self, *, operation_id, case, quarantine_id, assessment, actor_user_id):
        self._insert_assessment(operation_id, assessment, case, actor_user_id, quarantine_id)
        changed = self._db.execute(
            "UPDATE loss_cases SET status='TREATMENT_PENDING',updated_at=?,version=version+1 "
            "WHERE id=? AND status IN ('SUBMITTED','UNDER_REVIEW','TREATMENT_PENDING')",
            (self._now(), case["id"])).rowcount
        if changed != 1: raise LossStateTransitionError("El expediente cambió durante el bloqueo")
        self._event("LOSS_LOT_BLOCKED", operation_id, case, actor_user_id,
                    quarantine_id=quarantine_id, risk_level=assessment.risk_level.value)
        self._processed(operation_id, "BLOCK_AT_RISK_LOT", case["id"],
                        {"kind": "BLOCK", "entity_id": case["id"],
                         "quarantine_id": quarantine_id,
                         "risk_level": assessment.risk_level.value})

    def authorize_disposition(self, *, operation_id, case, method_code, quantity, weight,
                              reason, actor_user_id):
        disposition_id = new_uuid()
        self._db.execute(
            "INSERT INTO loss_dispositions (id,loss_case_id,operation_id,method_code,status,"
            "quantity,weight,authorized_by_user_id,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (disposition_id, case["id"], operation_id, method_code, "AUTHORIZED",
             str(quantity), str(weight), actor_user_id, self._now()))
        self._event("LOSS_DISPOSITION_AUTHORIZED", operation_id, case, actor_user_id,
                    disposition_id=disposition_id, quarantine_id=case["quarantine_id"],
                    reason=reason)
        self._processed(operation_id, "AUTHORIZE_LOT_DISPOSITION", disposition_id,
                        {"kind": "DISPOSITION_AUTHORIZED", "entity_id": disposition_id,
                         "disposition_id": disposition_id,
                         "quarantine_id": case["quarantine_id"]})
        return disposition_id

    def get_disposition(self, disposition_id):
        row = self._db.execute(
            "SELECT d.id,d.loss_case_id,ll.lot_id,d.status,d.authorized_by_user_id,"
            "ra.quarantine_id,d.method_code FROM loss_dispositions d "
            "JOIN loss_lines ll ON ll.loss_case_id=d.loss_case_id "
            "JOIN loss_lot_risk_assessments ra ON ra.loss_case_id=d.loss_case_id "
            "AND ra.lot_id=ll.lot_id AND ra.quarantine_id IS NOT NULL "
            "WHERE d.id=? ORDER BY ra.assessed_at DESC,ra.id DESC LIMIT 1",
            (disposition_id,)).fetchone()
        if not row: return None
        keys = ("id", "loss_case_id", "lot_id", "status", "authorized_by_user_id",
                "quarantine_id", "reason")
        return dict(zip(keys, row))

    def complete_disposition(self, *, operation_id, disposition, case,
                             certificate_reference, actor_user_id):
        changed = self._db.execute(
            "UPDATE loss_dispositions SET status='COMPLETED',completed_by_user_id=?,"
            "completed_at=?,certificate_reference=? WHERE id=? AND status='AUTHORIZED' "
            "AND authorized_by_user_id<>?",
            (actor_user_id, self._now(), certificate_reference, disposition["id"],
             actor_user_id)).rowcount
        if changed != 1: raise LossStateTransitionError("La disposición cambió durante su cierre")
        self._close_case(case["id"])
        self._event("LOSS_DISPOSITION_COMPLETED", operation_id, case, actor_user_id,
                    disposition_id=disposition["id"],
                    quarantine_id=disposition["quarantine_id"])
        self._processed(operation_id, "COMPLETE_LOT_DISPOSITION", disposition["id"],
                        {"kind": "DISPOSITION_COMPLETED", "entity_id": disposition["id"],
                         "disposition_id": disposition["id"],
                         "quarantine_id": disposition["quarantine_id"]})

    def _insert_assessment(self, operation_id, assessment, case, actor, quarantine_id):
        assessment_id = new_uuid()
        self._db.execute(
            "INSERT INTO loss_lot_risk_assessments (id,operation_id,loss_case_id,lot_id,"
            "product_id,branch_id,warehouse_id,risk_level,expiry_risk,damage_severity,"
            "expiration_date,days_to_expiry,quantity,weight,quarantine_id,assessed_by_user_id,"
            "assessed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (assessment_id, operation_id, case["id"], case["lot_id"], case["product_id"],
             case["branch_id"], case["warehouse_id"], assessment.risk_level.value,
             assessment.expiry_risk, assessment.damage_severity.value, case["expiration_date"],
             assessment.days_to_expiry, str(assessment.quantity), str(assessment.weight),
             quarantine_id, actor, self._now()))
        return assessment_id

    def _close_case(self, case_id):
        changed = self._db.execute(
            "UPDATE loss_cases SET status='CLOSED',closed_at=?,updated_at=?,version=version+1 "
            "WHERE id=? AND status='TREATMENT_PENDING'",
            (self._now(), self._now(), case_id)).rowcount
        if changed != 1: raise LossStateTransitionError("El expediente cambió durante el cierre")

    def _event(self, name, operation_id, case, actor, **extra):
        event = build_loss_event(name, operation_id=operation_id, entity_id=case["id"],
            branch_id=case["branch_id"], warehouse_id=case["warehouse_id"],
            user_id=actor, **extra)
        self._db.execute(
            "INSERT INTO loss_outbox (id,event_id,event_name,aggregate_id,operation_id,"
            "correlation_id,payload_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (new_uuid(), event["event_id"], name, case["id"], operation_id,
             event["event_id"], json.dumps(event, sort_keys=True), self._now()))

    def _processed(self, operation_id, operation_type, entity_id, result):
        self._db.execute(
            "INSERT INTO loss_processed_operations (operation_id,operation_type,"
            "result_entity_id,result_json,processed_at) VALUES (?,?,?,?,?)",
            (operation_id, operation_type, entity_id, json.dumps(result, sort_keys=True), self._now()))

    @staticmethod
    def _now(): return datetime.now(timezone.utc).isoformat()
