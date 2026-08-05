"""Persistence boundary for Losses ↔ Inventory workflow state and outbox."""
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.losses.exceptions import LossStateTransitionError
from backend.shared.ids import new_uuid


class LossInventoryRepository:
    def __init__(self, connection) -> None:
        self._db = connection

    @contextmanager
    def transaction(self):
        self._db.execute("SAVEPOINT loss6_inventory")
        try:
            yield
            self._db.execute("RELEASE SAVEPOINT loss6_inventory")
        except Exception:
            self._db.execute("ROLLBACK TO SAVEPOINT loss6_inventory")
            self._db.execute("RELEASE SAVEPOINT loss6_inventory")
            raise

    def find_processed(self, operation_id: str):
        row = self._db.execute(
            "SELECT result_entity_id,result_json FROM loss_processed_operations "
            "WHERE operation_id=?", (operation_id,)).fetchone()
        if not row:
            return None
        payload = json.loads(row[1])
        return str(row[0]), str(payload["status"]), payload.get("inventory_movement_id")

    def get_case_for_inventory(self, case_id: str):
        row = self._db.execute(
            "SELECT lc.id,lc.branch_id,lc.warehouse_id,lc.status,c.code,"
            "lc.requires_inventory_posting,lc.inventory_movement_id "
            "FROM loss_cases lc JOIN loss_classifications c ON c.id=lc.classification_id "
            "WHERE lc.id=?", (case_id,)).fetchone()
        if not row:
            return None
        return dict(zip(("id", "branch_id", "warehouse_id", "status", "classification",
                         "requires_inventory_posting", "inventory_movement_id"), row))

    def get_lines(self, case_id: str):
        rows = self._db.execute(
            "SELECT product_id,lot_id,quantity,weight,unit,location_id FROM loss_lines "
            "WHERE loss_case_id=? ORDER BY created_at,id", (case_id,)).fetchall()
        return [{"product_id": str(r[0]), "lot_id": r[1],
                 "quantity": Decimal(str(r[2])), "weight": Decimal(str(r[3])),
                 "unit": str(r[4]), "location_id": r[5]} for r in rows]

    def get_available_location(self, warehouse_id: str) -> str | None:
        row = self._db.execute(
            "SELECT id FROM storage_locations WHERE warehouse_id=? "
            "AND location_type='AVAILABLE' AND status='ACTIVE' LIMIT 1",
            (warehouse_id,)).fetchone()
        return str(row[0]) if row else None

    def has_posting_request(self, case_id: str) -> bool:
        return self._db.execute(
            "SELECT 1 FROM loss_outbox WHERE aggregate_id=? "
            "AND event_name='LOSS_INVENTORY_POSTING_REQUESTED' LIMIT 1",
            (case_id,)).fetchone() is not None

    def record_request(self, case_id: str, operation_id: str, event: dict):
        self._record(case_id, operation_id, "REQUEST_LOSS_INVENTORY_POSTING",
                     "APPROVED", None, event)

    def record_posted(self, case_id: str, operation_id: str,
                      movement_id: str, event: dict):
        changed = self._db.execute(
            "UPDATE loss_cases SET status='INVENTORY_POSTED',inventory_movement_id=?,"
            "updated_at=?,version=version+1 WHERE id=? AND status='APPROVED'",
            (movement_id, self._now(), case_id)).rowcount
        if changed != 1:
            raise LossStateTransitionError("El expediente cambió durante el posteo")
        self._record(case_id, operation_id, "POST_LOSS_INVENTORY",
                     "INVENTORY_POSTED", movement_id, event)

    def record_reversed(self, case_id: str, operation_id: str,
                        reversal_id: str, event: dict):
        changed = self._db.execute(
            "UPDATE loss_cases SET status='REVERSED',updated_at=?,version=version+1 "
            "WHERE id=? AND status='INVENTORY_POSTED'",
            (self._now(), case_id)).rowcount
        if changed != 1:
            raise LossStateTransitionError("El expediente cambió durante el reverso")
        self._record(case_id, operation_id, "REVERSE_LOSS_INVENTORY",
                     "REVERSED", reversal_id, event)

    def _record(self, case_id, operation_id, operation_type, status,
                movement_id, event):
        now = self._now()
        self._db.execute(
            "INSERT INTO loss_outbox (id,event_id,event_name,aggregate_id,operation_id,"
            "correlation_id,payload_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (new_uuid(), event["event_id"], event["event_name"], case_id,
             operation_id, event["event_id"],
             json.dumps(event, ensure_ascii=False, sort_keys=True), now))
        self._db.execute(
            "INSERT INTO loss_processed_operations (operation_id,operation_type,"
            "result_entity_id,result_json,processed_at) VALUES (?,?,?,?,?)",
            (operation_id, operation_type, case_id,
             json.dumps({"status": status, "inventory_movement_id": movement_id}), now))

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()
