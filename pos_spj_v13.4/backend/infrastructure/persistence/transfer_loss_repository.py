"""Persistence adapter for LOSS-12 transfer differences and claims."""

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal

from backend.shared.ids import new_uuid


class TransferLossRepository:
    def __init__(self, connection) -> None: self._db = connection

    @contextmanager
    def transaction(self):
        self._db.execute("SAVEPOINT loss12_transfer")
        try:
            yield
            self._db.execute("RELEASE SAVEPOINT loss12_transfer")
        except Exception:
            self._db.execute("ROLLBACK TO SAVEPOINT loss12_transfer")
            self._db.execute("RELEASE SAVEPOINT loss12_transfer")
            raise

    def find_processed(self, operation_id):
        row = self._db.execute(
            "SELECT result_json FROM loss_processed_operations WHERE operation_id=?",
            (operation_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def get_resolved_difference(self, *, transfer_id, difference_id, resolution_id):
        row = self._db.execute(
            "SELECT t.id,d.id,r.id,r.resolution_type,d.difference_type,d.responsible_stage,"
            "d.expected_quantity,d.actual_quantity,d.expected_weight,d.actual_weight,"
            "l.product_id,rr.lot_id,t.destination_branch_id,t.destination_warehouse_id,"
            "rr.receipt_id,tr.receipt_operation_id,"
            "EXISTS(SELECT 1 FROM inventory_ledger il WHERE il.movement_type='TRANSFER_RECEIPT' "
            "AND il.source_document_id=rr.receipt_id AND il.status='POSTED') "
            "FROM transfer_differences d JOIN stock_transfers t ON t.id=d.transfer_id "
            "JOIN stock_transfer_lines l ON l.id=d.transfer_line_id "
            "JOIN transfer_difference_resolutions r ON r.difference_id=d.id "
            "LEFT JOIN transfer_receipt_lines rr ON rr.transfer_line_id=l.id "
            "LEFT JOIN transfer_receipts tr ON tr.id=rr.receipt_id "
            "WHERE t.id=? AND d.id=? AND r.id=? AND d.status='RESOLVED' "
            "ORDER BY tr.received_at DESC LIMIT 1",
            (transfer_id, difference_id, resolution_id)).fetchone()
        if not row: return None
        keys = ("transfer_id", "difference_id", "resolution_id", "resolution_type",
                "difference_type", "responsible_stage", "expected_quantity", "actual_quantity",
                "expected_weight", "actual_weight", "product_id", "lot_id", "branch_id",
                "warehouse_id", "receipt_id", "receipt_operation_id", "inventory_receipt_posted")
        result = dict(zip(keys, row))
        for key in ("expected_quantity", "actual_quantity", "expected_weight", "actual_weight"):
            result[key] = Decimal(str(result[key]))
        result["inventory_receipt_posted"] = bool(result["inventory_receipt_posted"])
        return result

    def resolve_reason_id(self, classification):
        row = self._db.execute(
            "SELECT r.id FROM loss_reasons r JOIN loss_classifications c "
            "ON c.id=r.classification_id WHERE c.code=? AND c.active=1 AND r.active=1 "
            "ORDER BY r.display_name LIMIT 1", (classification,)).fetchone()
        return str(row[0]) if row else None

    def save_transfer_loss(self, *, operation_id, case, fact, assessment, event,
                           inventory_effect):
        now = self._now()
        classification_id = self._db.execute(
            "SELECT id FROM loss_classifications WHERE code=? AND active=1",
            (case.classification.value,)).fetchone()[0]
        self._db.execute(
            "INSERT INTO loss_cases (id,operation_id,branch_id,warehouse_id,reported_by_user_id,"
            "classification_id,reason_id,origin,status,requires_inventory_posting,gross_value,"
            "recoverable_value,net_loss_value,source_module,source_document_type,source_document_id,"
            "notes,occurred_at,submitted_at,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (case.id, operation_id, case.branch_id, case.warehouse_id, case.reported_by_user_id,
             classification_id, case.reason_id, case.origin.value, case.status.value, 0,
             "0", "0", "0", "transfers", "TRANSFER_DIFFERENCE", fact["difference_id"],
             case.notes, case.created_at.isoformat(), now, case.created_at.isoformat(), now))
        line = case.lines[0]
        self._db.execute(
            "INSERT INTO loss_lines (id,loss_case_id,product_id,lot_id,quantity,weight,unit,"
            "unit_cost,gross_value,recoverable_value,net_loss_value,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (line.id, case.id, line.product_id, line.lot_id, str(line.quantity), str(line.weight),
             line.unit, "0", "0", "0", "0", now))
        self._db.execute(
            "INSERT INTO loss_transfer_links (id,loss_case_id,transfer_id,difference_id,"
            "resolution_id,receipt_id,receipt_operation_id,difference_type,responsible_stage,"
            "suggested_party_type,inventory_effect,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (new_uuid(), case.id, fact["transfer_id"], fact["difference_id"], fact["resolution_id"],
             fact["receipt_id"], fact["receipt_operation_id"], fact["difference_type"],
             assessment.responsible_stage, assessment.suggested_party_type.value,
             inventory_effect, now))
        self._outbox(case.id, operation_id, event)
        self._processed(operation_id, "REGISTER_TRANSFER_LOSS", case.id,
                        {"entity_id": case.id, "status": case.status.value})

    def get_transfer_loss(self, case_id):
        row = self._db.execute(
            "SELECT l.loss_case_id,c.branch_id,c.warehouse_id,l.transfer_id "
            "FROM loss_transfer_links l JOIN loss_cases c ON c.id=l.loss_case_id "
            "WHERE l.loss_case_id=?", (case_id,)).fetchone()
        return (dict(zip(("case_id", "branch_id", "warehouse_id", "transfer_id"), row))
                if row else None)

    def save_claim(self, *, claim_id, operation_id, loss_case_id, transfer_id,
                   party_type, responsible_party_id, claimed_value, reason, evidence,
                   actor_user_id, event):
        now = self._now()
        self._db.execute(
            "INSERT INTO loss_transfer_claims (id,operation_id,loss_case_id,transfer_id,"
            "party_type,responsible_party_id,claimed_value,status,reason,evidence_json,"
            "created_by_user_id,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (claim_id, operation_id, loss_case_id, transfer_id, party_type,
             responsible_party_id, str(claimed_value), "OPEN", reason,
             json.dumps(tuple(evidence), ensure_ascii=False), actor_user_id, now))
        self._outbox(loss_case_id, operation_id, event)
        self._processed(operation_id, "OPEN_TRANSFER_CLAIM", claim_id,
                        {"entity_id": claim_id, "status": "OPEN"})

    def _outbox(self, aggregate_id, operation_id, event):
        self._db.execute(
            "INSERT INTO loss_outbox (id,event_id,event_name,aggregate_id,operation_id,"
            "correlation_id,payload_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (new_uuid(), event["event_id"], event["event_name"], aggregate_id, operation_id,
             event["event_id"], json.dumps(event, ensure_ascii=False, sort_keys=True), self._now()))

    def _processed(self, operation_id, operation_type, entity_id, result):
        self._db.execute(
            "INSERT INTO loss_processed_operations (operation_id,operation_type,result_entity_id,"
            "result_json,processed_at) VALUES (?,?,?,?,?)",
            (operation_id, operation_type, entity_id, json.dumps(result, sort_keys=True), self._now()))

    @staticmethod
    def _now(): return datetime.now(timezone.utc).isoformat()
