"""Persistence boundary for LOSS-11 quality inspections and evidence."""

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.losses.events import build_loss_event
from backend.domain.losses.exceptions import LossStateTransitionError
from backend.shared.ids import new_uuid


class QualityControlRepository:
    def __init__(self, connection) -> None: self._db = connection

    @contextmanager
    def transaction(self):
        self._db.execute("SAVEPOINT loss11_quality")
        try:
            yield
            self._db.execute("RELEASE SAVEPOINT loss11_quality")
        except Exception:
            self._db.execute("ROLLBACK TO SAVEPOINT loss11_quality")
            self._db.execute("RELEASE SAVEPOINT loss11_quality")
            raise

    def find_processed(self, operation_id):
        row = self._db.execute(
            "SELECT result_json FROM loss_processed_operations WHERE operation_id=?",
            (operation_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def get_quality_case(self, case_id, lot_id):
        row = self._db.execute(
            "SELECT lc.id,lc.branch_id,lc.warehouse_id,lc.status,c.code,ll.product_id,"
            "ll.lot_id,ll.quantity,ll.weight,q.id,q.created_by_user_id "
            "FROM loss_cases lc JOIN loss_classifications c ON c.id=lc.classification_id "
            "JOIN loss_lines ll ON ll.loss_case_id=lc.id LEFT JOIN inventory_quarantine q "
            "ON q.id=(SELECT iq.id FROM inventory_quarantine iq WHERE iq.lot_id=ll.lot_id "
            "AND iq.status IN ('OPEN','UNDER_REVIEW','PARTIALLY_RELEASED') "
            "ORDER BY iq.created_at DESC,iq.id DESC LIMIT 1) "
            "WHERE lc.id=? AND ll.lot_id=? ORDER BY ll.created_at,ll.id LIMIT 1",
            (case_id, lot_id)).fetchone()
        if not row: return None
        keys = ("id", "branch_id", "warehouse_id", "status", "classification",
                "product_id", "lot_id", "quantity", "weight", "quarantine_id",
                "blocked_by_user_id")
        result = dict(zip(keys, row))
        result["quantity"] = Decimal(str(result["quantity"]))
        result["weight"] = Decimal(str(result["weight"]))
        return result

    def record_rejection(self, *, operation_id, case, evaluation, evidence, notes,
                         quarantine_id, temperature_reading_id, actor_user_id):
        assessment_id = self._assessment(operation_id, case, evaluation, notes,
            quarantine_id, temperature_reading_id, actor_user_id, None)
        self._evidence(assessment_id, case["id"], evidence, actor_user_id)
        changed = self._db.execute(
            "UPDATE loss_cases SET status='TREATMENT_PENDING',updated_at=?,version=version+1 "
            "WHERE id=? AND status IN ('SUBMITTED','UNDER_REVIEW')",
            (self._now(), case["id"])).rowcount
        if changed != 1: raise LossStateTransitionError("El expediente cambió durante el rechazo")
        self._event("LOSS_QUALITY_REJECTED", operation_id, case, actor_user_id,
                    quarantine_id=quarantine_id, contamination=evaluation.contamination_level.value,
                    temperature_reading_id=temperature_reading_id)
        self._processed(operation_id, "QUALITY_REJECTION", case["id"],
            {"case_id": case["id"], "status": "REJECTED", "quarantine_id": quarantine_id,
             "temperature_reading_id": temperature_reading_id})

    def record_condemnation(self, *, operation_id, case, evaluation, evidence, notes,
                            temperature_reading_id, actor_user_id):
        assessment_id = self._assessment(operation_id, case, evaluation, notes,
            case["quarantine_id"], temperature_reading_id, actor_user_id, None)
        self._evidence(assessment_id, case["id"], evidence, actor_user_id)
        # La condena conserva la cuarentena para el flujo canónico LOSS-14.
        self._event("LOSS_QUALITY_CONDEMNED", operation_id, case, actor_user_id,
                    quarantine_id=case["quarantine_id"],
                    contamination=evaluation.contamination_level.value,
                    temperature_reading_id=temperature_reading_id)
        self._processed(operation_id, "QUALITY_CONDEMNATION", case["id"],
            {"case_id": case["id"], "status": "CONDEMNED_PENDING_DISPOSITION",
             "quarantine_id": case["quarantine_id"],
             "temperature_reading_id": temperature_reading_id})

    def _assessment(self, operation_id, case, evaluation, notes, quarantine_id,
                    reading_id, actor, disposition_id):
        assessment_id = new_uuid()
        self._db.execute(
            "INSERT INTO loss_quality_assessments (id,operation_id,loss_case_id,lot_id,"
            "decision,contamination_level,temperature,minimum_temperature,maximum_temperature,"
            "temperature_out_of_range,temperature_reading_id,quarantine_id,disposition_id,"
            "notes,decided_by_user_id,decided_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (assessment_id, operation_id, case["id"], case["lot_id"],
             evaluation.decision.value, evaluation.contamination_level.value,
             None if evaluation.temperature is None else str(evaluation.temperature),
             None if evaluation.minimum_temperature is None else str(evaluation.minimum_temperature),
             None if evaluation.maximum_temperature is None else str(evaluation.maximum_temperature),
             1 if evaluation.temperature_out_of_range else 0, reading_id, quarantine_id,
             disposition_id, notes, actor, self._now()))
        return assessment_id

    def _evidence(self, assessment_id, case_id, items, actor):
        for item in items:
            evidence_id = new_uuid()
            self._db.execute(
                "INSERT INTO loss_evidence (id,loss_case_id,evidence_type,storage_uri,checksum,"
                "captured_by_user_id,captured_at,metadata_json) VALUES (?,?,?,?,?,?,?,?)",
                (evidence_id, case_id, item.evidence_type.strip(), item.storage_uri.strip(),
                 item.checksum.strip().lower(), actor, self._now(), item.metadata_json))
            self._db.execute(
                "INSERT INTO loss_quality_evidence (quality_assessment_id,evidence_id) VALUES (?,?)",
                (assessment_id, evidence_id))

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
            "INSERT INTO loss_processed_operations (operation_id,operation_type,result_entity_id,"
            "result_json,processed_at) VALUES (?,?,?,?,?)",
            (operation_id, operation_type, entity_id, json.dumps(result, sort_keys=True), self._now()))

    @staticmethod
    def _now(): return datetime.now(timezone.utc).isoformat()
