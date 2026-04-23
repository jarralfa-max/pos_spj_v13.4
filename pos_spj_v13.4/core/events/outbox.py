from __future__ import annotations

import json
from datetime import datetime
from typing import List, Dict, Any


def ensure_outbox_table(db) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS event_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            aggregate_type TEXT DEFAULT '',
            aggregate_id TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'PENDING',
            error TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            dispatched_at TEXT
        )
        """
    )
    try:
        db.commit()
    except Exception:
        pass


def enqueue_event(
    db,
    event_type: str,
    payload: Dict[str, Any],
    aggregate_type: str = "",
    aggregate_id: str = "",
) -> int:
    ensure_outbox_table(db)
    cur = db.execute(
        """
        INSERT INTO event_outbox
        (event_type, payload, aggregate_type, aggregate_id, status, created_at)
        VALUES (?,?,?,?, 'PENDING', ?)
        """,
        (
            event_type,
            json.dumps(payload or {}, ensure_ascii=False, default=str),
            aggregate_type or "",
            str(aggregate_id or ""),
            datetime.utcnow().isoformat(),
        ),
    )
    try:
        db.commit()
    except Exception:
        pass
    return int(cur.lastrowid)


def fetch_pending(db, limit: int = 100) -> List[dict]:
    ensure_outbox_table(db)
    rows = db.execute(
        """
        SELECT id, event_type, payload, aggregate_type, aggregate_id, created_at
        FROM event_outbox
        WHERE status='PENDING'
        ORDER BY id ASC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "id": r["id"] if hasattr(r, "__getitem__") else r[0],
                "event_type": r["event_type"] if hasattr(r, "__getitem__") else r[1],
                "payload": json.loads(r["payload"] if hasattr(r, "__getitem__") else r[2]),
                "aggregate_type": r["aggregate_type"] if hasattr(r, "__getitem__") else r[3],
                "aggregate_id": r["aggregate_id"] if hasattr(r, "__getitem__") else r[4],
                "created_at": r["created_at"] if hasattr(r, "__getitem__") else r[5],
            }
        )
    return out


def mark_dispatched(db, event_id: int, error: str = "") -> None:
    status = "ERROR" if error else "DISPATCHED"
    db.execute(
        """
        UPDATE event_outbox
        SET status=?, error=?, dispatched_at=?
        WHERE id=?
        """,
        (status, error or "", datetime.utcnow().isoformat(), int(event_id)),
    )
    try:
        db.commit()
    except Exception:
        pass

