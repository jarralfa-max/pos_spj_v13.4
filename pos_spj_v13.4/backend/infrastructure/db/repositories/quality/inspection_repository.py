"""Persistencia de inspecciones de Calidad y de su outbox."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.shared.ids import new_uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Inspection:
    id: str
    operation_id: str
    source_module: str
    source_document_id: str
    subject_type: str
    subject_id: str
    product_id: str
    lot_id: str | None
    branch_id: str
    warehouse_id: str
    produced_by_user_id: str
    status: str
    decided_by_user_id: str | None
    decision_operation_id: str | None
    reason: str | None


_COLS = ("id, operation_id, source_module, source_document_id, subject_type, subject_id,"
         " product_id, lot_id, branch_id, warehouse_id, produced_by_user_id, status,"
         " decided_by_user_id, decision_operation_id, reason")


class InspectionRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    def add(self, *, operation_id: str, source_module: str, source_document_id: str,
            subject_type: str, subject_id: str, product_id: str, lot_id: str | None,
            branch_id: str, warehouse_id: str, produced_by_user_id: str) -> str:
        inspection_id = new_uuid()
        self._conn.execute(
            "INSERT INTO quality_inspections (id, operation_id, source_module,"
            " source_document_id, subject_type, subject_id, product_id, lot_id, branch_id,"
            " warehouse_id, produced_by_user_id, status, requested_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,'PENDING',?)",
            (inspection_id, operation_id, source_module, source_document_id, subject_type,
             subject_id, product_id, lot_id, branch_id, warehouse_id, produced_by_user_id,
             _now()))
        return inspection_id

    def get(self, inspection_id: str) -> Inspection | None:
        fila = self._conn.execute(f"SELECT {_COLS} FROM quality_inspections WHERE id=?",
                                  (inspection_id,)).fetchone()
        return None if fila is None else Inspection(*tuple(fila))

    def find_by_subject(self, subject_type: str, subject_id: str) -> Inspection | None:
        fila = self._conn.execute(
            f"SELECT {_COLS} FROM quality_inspections WHERE subject_type=? AND subject_id=?",
            (subject_type, subject_id)).fetchone()
        return None if fila is None else Inspection(*tuple(fila))

    def list_pending(self, *, branch_id: str) -> list[Inspection]:
        return [Inspection(*tuple(f)) for f in self._conn.execute(
            f"SELECT {_COLS} FROM quality_inspections WHERE status='PENDING' AND branch_id=?"
            " ORDER BY requested_at", (branch_id,)).fetchall()]

    def decide(self, inspection_id: str, *, status: str, decided_by_user_id: str,
               decision_operation_id: str, reason: str) -> None:
        self._conn.execute(
            "UPDATE quality_inspections SET status=?, decided_by_user_id=?,"
            " decision_operation_id=?, reason=?, decided_at=? WHERE id=? AND status='PENDING'",
            (status, decided_by_user_id, decision_operation_id, reason, _now(), inspection_id))


class QualityOutboxRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    def enqueue(self, *, event_id: str, event_name: str, payload: dict,
                operation_id: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO quality_outbox (id, event_id, event_name, payload_json,"
            " operation_id, status, created_at) VALUES (?,?,?,?,?,'PENDING',?)",
            (new_uuid(), event_id, event_name, json.dumps(payload), operation_id, _now()))

    def list_pending(self, *, limit: int = 500) -> list[dict]:
        cur = self._conn.execute(
            "SELECT id, event_id, event_name, payload_json, operation_id FROM quality_outbox"
            " WHERE status='PENDING' ORDER BY created_at, id LIMIT ?", (limit,))
        columnas = [c[0] for c in cur.description]
        return [dict(zip(columnas, r)) for r in cur.fetchall()]

    def mark_dispatched(self, outbox_id: str) -> None:
        self._conn.execute(
            "UPDATE quality_outbox SET status='DISPATCHED', dispatched_at=? WHERE id=?",
            (_now(), outbox_id))

    def mark_failed(self, outbox_id: str, error: str) -> None:
        self._conn.execute(
            "UPDATE quality_outbox SET attempts=attempts+1, last_error=? WHERE id=?",
            (str(error)[:500], outbox_id))
