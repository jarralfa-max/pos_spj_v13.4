"""Support repositories: audit log, processed events, transactional outbox."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.infrastructure.db.repositories.hr.base import HRRepositoryBase
from backend.shared.ids import new_uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class HRAuditRepository(HRRepositoryBase):
    def record(self, *, action: str, actor_user_id: str | None, entity_type: str,
               entity_id: str | None, detail: str, operation_id: str | None = None) -> None:
        self._execute(
            "INSERT INTO hr_audit_log (id, action, actor_user_id, entity_type,"
            " entity_id, detail, operation_id, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (new_uuid(), action, actor_user_id, entity_type, entity_id, detail,
             operation_id, _now()))

    def list_for_entity(self, entity_type: str, entity_id: str) -> list[dict]:
        return self._query(
            "SELECT action, actor_user_id, detail, created_at FROM hr_audit_log"
            " WHERE entity_type=? AND entity_id=? ORDER BY created_at DESC",
            (entity_type, entity_id))


class HRProcessedEventRepository(HRRepositoryBase):
    def was_processed(self, event_id: str) -> bool:
        return self._query_one(
            "SELECT event_id FROM hr_processed_events WHERE event_id=?", (event_id,)) is not None

    def mark_processed(self, event_id: str, event_name: str, operation_id: str) -> None:
        self._execute(
            "INSERT INTO hr_processed_events (event_id, event_name, operation_id, processed_at)"
            " VALUES (?,?,?,?)", (event_id, event_name, operation_id, _now()))


class HRInboxRepository(HRRepositoryBase):
    """HR-06: eventos de otro contexto que RR. HH. aún no pudo aplicar (p. ej.
    apertura de caja de un usuario sin empleado vinculado). No se pierden ni se
    marcan procesados: se reprocesan al corregir la causa."""

    def hold(self, *, event_id: str, event_name: str, payload_json: str,
             user_id: str | None, error: str) -> None:
        self._execute(
            "INSERT INTO hr_inbox (event_id, event_name, payload_json, user_id, status,"
            " attempts, last_error, created_at) VALUES (?,?,?,?, 'PENDING', 1, ?, ?)"
            " ON CONFLICT(event_id) DO UPDATE SET attempts=attempts+1,"
            " last_error=excluded.last_error, status='PENDING'",
            (event_id, event_name, payload_json, user_id, error, _now()))

    def mark_processed(self, event_id: str) -> None:
        self._execute(
            "UPDATE hr_inbox SET status='PROCESSED', processed_at=?, last_error=NULL"
            " WHERE event_id=?", (_now(), event_id))

    def list_pending(self, *, user_id: str | None = None) -> list[dict]:
        if user_id:
            return self._query(
                "SELECT event_id, event_name, payload_json, user_id, attempts, last_error,"
                " created_at FROM hr_inbox WHERE status='PENDING' AND user_id=?"
                " ORDER BY created_at", (user_id,))
        return self._query(
            "SELECT event_id, event_name, payload_json, user_id, attempts, last_error,"
            " created_at FROM hr_inbox WHERE status='PENDING' ORDER BY created_at")


class HRCalendarRepository(HRRepositoryBase):
    """HR-22: zona horaria de la sucursal (perfil de sucursal → empresa →
    America/Mexico_City). Lee los perfiles de Configuración sólo si existen."""

    def timezone_name(self, branch_id: str | None) -> str:
        from backend.shared.business_dates import DEFAULT_BUSINESS_TIMEZONE
        for sql, params in (
            ("SELECT timezone FROM branch_profiles WHERE branch_id=? OR id=? LIMIT 1",
             (branch_id, branch_id)),
            ("SELECT default_timezone FROM company_profiles WHERE active=1 LIMIT 1", ()),
        ):
            if sql.startswith("SELECT timezone") and not branch_id:
                continue
            try:
                row = self._conn.execute(sql, params).fetchone()
            except Exception:
                continue
            if row and str(row[0] or "").strip():
                return str(row[0]).strip()
        return DEFAULT_BUSINESS_TIMEZONE


class HROutboxRepository(HRRepositoryBase):
    def enqueue(self, event_id: str, event_name: str, payload_json: str, operation_id: str) -> None:
        self._execute(
            "INSERT INTO hr_outbox (id, event_id, event_name, payload_json, operation_id,"
            " status, created_at) VALUES (?,?,?,?,?, 'PENDING', ?)",
            (new_uuid(), event_id, event_name, payload_json, operation_id, _now()))

    def list_pending(self, limit: int = 100) -> list[dict]:
        return self._query(
            "SELECT id, event_id, event_name, payload_json, operation_id, created_at"
            " FROM hr_outbox WHERE status='PENDING' ORDER BY created_at LIMIT ?", (limit,))

    def find_pending(self, event_name: str, needle: str) -> dict | None:
        """Evento PENDIENTE de ese nombre cuyo payload menciona ``needle``."""
        for row in self._query(
                "SELECT id, event_id, payload_json FROM hr_outbox WHERE status='PENDING'"
                " AND event_name=? ORDER BY created_at", (event_name,)):
            if needle in str(row["payload_json"]):
                return row
        return None

    def void(self, outbox_id: str, reason: str) -> None:
        """Nunca se entregará (p. ej. nómina revertida antes de contabilizar):
        sale de la cola con su motivo visible."""
        columns = {r[1] for r in self._conn.execute("PRAGMA table_info(hr_outbox)")}
        if "last_error" in columns:
            self._execute("UPDATE hr_outbox SET status='DISPATCHED', dispatched_at=?,"
                          " last_error=? WHERE id=?", (_now(), f"anulado: {reason}", outbox_id))
        else:
            self._execute("UPDATE hr_outbox SET status='DISPATCHED', dispatched_at=? WHERE id=?",
                          (_now(), outbox_id))

    def mark_dispatched(self, outbox_id: str) -> None:
        self._execute(
            "UPDATE hr_outbox SET status='DISPATCHED', dispatched_at=? WHERE id=?",
            (_now(), outbox_id))
