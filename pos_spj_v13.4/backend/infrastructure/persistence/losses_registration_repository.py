"""SQLite adapter for LOSS-5. All writes share one savepoint."""

import json
from datetime import datetime, timezone

from backend.domain.losses.policies import LossRegistrationPolicy
from backend.shared.ids import new_uuid


class LossRegistrationRepository:
    def __init__(self, connection) -> None:
        self._db = connection

    def find_processed(self, operation_id: str):
        row = self._db.execute(
            "SELECT result_entity_id, result_json FROM loss_processed_operations "
            "WHERE operation_id=?", (operation_id,)).fetchone()
        if not row:
            return None
        payload = json.loads(row[1])
        return str(row[0]), str(payload["status"])

    def resolve_reason(self, classification_id: str, reason_id: str):
        row = self._db.execute(
            "SELECT c.code, r.requires_evidence FROM loss_reasons r "
            "JOIN loss_classifications c ON c.id=r.classification_id "
            "WHERE c.id=? AND r.id=? AND c.active=1 AND r.active=1",
            (classification_id, reason_id),).fetchone()
        return (str(row[0]), bool(row[1])) if row else None

    def save(self, case, evidence: tuple[dict, ...], event: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        classification_id = self._db.execute(
            "SELECT id FROM loss_classifications WHERE code=? AND active=1",
            (case.classification.value,),).fetchone()[0]
        recoverable = sum((line.recoverable_value for line in case.lines), start=0)
        submitted_at = now if case.status.value == "SUBMITTED" else None
        self._db.execute("SAVEPOINT loss5_register")
        try:
            self._db.execute(
                "INSERT INTO loss_cases (id,operation_id,branch_id,warehouse_id,"
                "reported_by_user_id,classification_id,reason_id,origin,status,"
                "requires_inventory_posting,gross_value,recoverable_value,net_loss_value,"
                "notes,occurred_at,submitted_at,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (case.id, case.operation_id, case.branch_id, case.warehouse_id,
                 case.reported_by_user_id, classification_id, case.reason_id,
                 case.origin.value, case.status.value,
                 int(LossRegistrationPolicy().requires_inventory_posting(case.classification)),
                 str(case.gross_value), str(recoverable), str(case.net_loss_value),
                 case.notes, case.created_at.isoformat(), submitted_at,
                 case.created_at.isoformat(), now))
            for line in case.lines:
                self._db.execute(
                    "INSERT INTO loss_lines (id,loss_case_id,product_id,lot_id,quantity,"
                    "weight,unit,unit_cost,gross_value,recoverable_value,net_loss_value,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (line.id, case.id, line.product_id, line.lot_id,
                     str(line.quantity), str(line.weight), line.unit, str(line.unit_cost),
                     str(line.gross_value), str(line.recoverable_value),
                     str(line.net_loss_value), now))
            for item in evidence:
                self._db.execute(
                    "INSERT INTO loss_evidence (id,loss_case_id,evidence_type,storage_uri,"
                    "checksum,captured_by_user_id,captured_at,metadata_json) VALUES (?,?,?,?,?,?,?,?)",
                    tuple(item[key] for key in ("id", "loss_case_id", "evidence_type",
                                                "storage_uri", "checksum",
                                                "captured_by_user_id", "captured_at",
                                                "metadata_json")))
            self._db.execute(
                "INSERT INTO loss_outbox (id,event_id,event_name,aggregate_id,operation_id,"
                "correlation_id,payload_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (new_uuid(), event["event_id"], event["event_name"], case.id,
                 case.operation_id, event["event_id"],
                 json.dumps(event, ensure_ascii=False, sort_keys=True), now))
            result_json = json.dumps({"status": case.status.value})
            self._db.execute(
                "INSERT INTO loss_processed_operations (operation_id,operation_type,"
                "result_entity_id,result_json,processed_at) VALUES (?,?,?,?,?)",
                (case.operation_id, "REGISTER_GENERAL_LOSS", case.id, result_json, now))
            self._db.execute("RELEASE SAVEPOINT loss5_register")
        except Exception:
            self._db.execute("ROLLBACK TO SAVEPOINT loss5_register")
            self._db.execute("RELEASE SAVEPOINT loss5_register")
            raise


class LossRegistrationQueryRepository:
    def __init__(self, connection) -> None:
        self._db = connection

    def search_products(self, query: str, limit: int = 20):
        term = f"%{query.strip()}%"
        return self._db.execute(
            "SELECT id,name,COALESCE(sku,'') FROM products "
            "WHERE active=1 AND (name LIKE ? OR sku LIKE ?) ORDER BY name LIMIT ?",
            (term, term, limit)).fetchall()

    def search_lots(self, product_id: str, query: str, limit: int = 20):
        term = f"%{query.strip()}%"
        return self._db.execute(
            "SELECT id,lot_code,COALESCE(expiration_date,'') FROM inventory_lots "
            "WHERE product_id=? AND lot_code LIKE ? "
            "ORDER BY expiration_date LIMIT ?", (product_id, term, limit)).fetchall()

    def classifications(self):
        return self._db.execute(
            "SELECT id,display_name FROM loss_classifications WHERE active=1 "
            "ORDER BY display_name").fetchall()

    def reasons(self, classification_id: str):
        return self._db.execute(
            "SELECT id,display_name,requires_evidence FROM loss_reasons "
            "WHERE classification_id=? AND active=1 ORDER BY display_name",
            (classification_id,)).fetchall()
