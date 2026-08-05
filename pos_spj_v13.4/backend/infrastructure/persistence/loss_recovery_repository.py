"""Persistence adapter for the approved LOSS-13 recovery workflow."""

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal

from backend.shared.ids import new_uuid


class LossRecoveryRepository:
    def __init__(self, connection) -> None: self._db = connection

    @contextmanager
    def transaction(self):
        self._db.execute("SAVEPOINT loss13_recovery")
        try:
            yield
            self._db.execute("RELEASE SAVEPOINT loss13_recovery")
        except Exception:
            self._db.execute("ROLLBACK TO SAVEPOINT loss13_recovery")
            self._db.execute("RELEASE SAVEPOINT loss13_recovery")
            raise

    def find_processed(self, operation_id):
        row = self._db.execute(
            "SELECT result_json FROM loss_processed_operations WHERE operation_id=?",
            (operation_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def get_case(self, case_id):
        row = self._db.execute(
            "SELECT c.id,c.branch_id,c.warehouse_id,c.status,c.gross_value,c.recoverable_value,"
            "q.id,q.quantity,q.weight,"
            "(SELECT COALESCE(SUM(CAST(quantity AS NUMERIC)),0) FROM loss_lines WHERE loss_case_id=c.id),"
            "(SELECT COALESCE(SUM(CAST(weight AS NUMERIC)),0) FROM loss_lines WHERE loss_case_id=c.id),"
            "(SELECT COALESCE(SUM(CAST(quantity AS NUMERIC)),0) FROM loss_recoveries WHERE loss_case_id=c.id AND status='APPROVED'),"
            "(SELECT COALESCE(SUM(CAST(weight AS NUMERIC)),0) FROM loss_recoveries WHERE loss_case_id=c.id AND status='APPROVED') "
            "FROM loss_cases c LEFT JOIN inventory_quarantine q ON q.id=("
            "SELECT iq.id FROM inventory_quarantine iq JOIN loss_lines ll ON ll.lot_id=iq.lot_id "
            "WHERE ll.loss_case_id=c.id AND iq.status IN ('OPEN','UNDER_REVIEW','PARTIALLY_RELEASED') "
            "ORDER BY iq.created_at DESC,iq.id DESC LIMIT 1) WHERE c.id=?", (case_id,)).fetchone()
        if not row: return None
        keys = ("id", "branch_id", "warehouse_id", "status", "gross_value",
                "recovered_value", "quarantine_id", "quarantine_quantity", "quarantine_weight",
                "loss_quantity", "loss_weight", "recovered_quantity", "recovered_weight")
        result = dict(zip(keys, row))
        for key in ("gross_value", "recovered_value", "quarantine_quantity", "quarantine_weight",
                    "loss_quantity", "loss_weight", "recovered_quantity", "recovered_weight"):
            result[key] = Decimal(str(result[key] or "0"))
        return result

    def save_pending(self, *, recovery_id, operation_id, case, plan, reference_id,
                     target_product_id, notes, actor_user_id, event):
        now = self._now()
        self._db.execute(
            "INSERT INTO loss_recoveries (id,loss_case_id,operation_id,recovery_type,quantity,"
            "weight,recovered_value,reference_id,recorded_by_user_id,recorded_at,status,"
            "target_product_id,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (recovery_id, case["id"], operation_id, plan.recovery_type.value,
             str(plan.quantity), str(plan.weight), str(plan.recovered_value), reference_id,
             actor_user_id, now, "PENDING_APPROVAL", target_product_id, notes))
        self._outbox(case["id"], operation_id, event)
        self._processed(operation_id, "SUBMIT_LOSS_RECOVERY", recovery_id,
                        {"entity_id": recovery_id, "status": "PENDING_APPROVAL"})

    def get_recovery(self, recovery_id):
        row = self._db.execute(
            "SELECT id,loss_case_id,recovery_type,quantity,weight,recovered_value,reference_id,"
            "target_product_id,status,recorded_by_user_id FROM loss_recoveries WHERE id=?",
            (recovery_id,)).fetchone()
        if not row: return None
        keys = ("id", "loss_case_id", "recovery_type", "quantity", "weight",
                "recovered_value", "reference_id", "target_product_id", "status",
                "recorded_by_user_id")
        result = dict(zip(keys, row))
        for key in ("quantity", "weight", "recovered_value"):
            result[key] = Decimal(str(result[key]))
        return result

    def validate_reference(self, recovery_type, reference_id, target_product_id):
        if recovery_type == "CLAIM":
            return self._db.execute(
                "SELECT id FROM loss_transfer_claims WHERE id=? AND status='PAID'",
                (reference_id,)).fetchone()
        return self._db.execute(
            "SELECT l.id FROM inventory_ledger l JOIN inventory_ledger_lines ll "
            "ON ll.movement_id=l.id WHERE l.id=? AND l.status='POSTED' AND ll.product_id=?",
            (reference_id, target_product_id)).fetchone()

    def approve(self, *, recovery_id, operation_id, case, approved_by_user_id,
                approval_reason, event):
        now = self._now()
        recovery = self.get_recovery(recovery_id)
        changed = self._db.execute(
            "UPDATE loss_recoveries SET status='APPROVED',approved_by_user_id=?,approved_at=?,"
            "approval_reason=? WHERE id=? AND status='PENDING_APPROVAL' "
            "AND recorded_by_user_id<>?",
            (approved_by_user_id, now, approval_reason, recovery_id,
             approved_by_user_id)).rowcount
        if changed != 1: raise RuntimeError("La recuperación cambió durante su aprobación")
        new_recovered = case["recovered_value"] + recovery["recovered_value"]
        remaining = case["gross_value"] - new_recovered
        status_sql = ",status='CLOSED',closed_at=?" if remaining == 0 else ""
        parameters = [str(new_recovered), str(remaining), now]
        if remaining == 0: parameters.append(now)
        parameters.append(case["id"])
        self._db.execute(
            "UPDATE loss_cases SET recoverable_value=?,net_loss_value=?,updated_at=?,"
            "version=version+1" + status_sql + " WHERE id=?",
            tuple(parameters))
        self._outbox(case["id"], operation_id, event)
        self._processed(operation_id, "APPROVE_LOSS_RECOVERY", recovery_id,
                        {"entity_id": recovery_id, "status": "APPROVED"})

    def _outbox(self, aggregate_id, operation_id, event):
        self._db.execute(
            "INSERT INTO loss_outbox (id,event_id,event_name,aggregate_id,operation_id,"
            "correlation_id,payload_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (new_uuid(), event["event_id"], event["event_name"], aggregate_id,
             operation_id, event["event_id"], json.dumps(event, sort_keys=True), self._now()))

    def _processed(self, operation_id, operation_type, entity_id, result):
        self._db.execute(
            "INSERT INTO loss_processed_operations (operation_id,operation_type,result_entity_id,"
            "result_json,processed_at) VALUES (?,?,?,?,?)",
            (operation_id, operation_type, entity_id, json.dumps(result, sort_keys=True), self._now()))

    @staticmethod
    def _now(): return datetime.now(timezone.utc).isoformat()
