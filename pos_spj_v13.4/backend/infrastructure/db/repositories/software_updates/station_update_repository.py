"""SQLite persistence for the station's update settings, the update event
trail and the "is something in progress?" probe. Repositories never commit;
the use case does."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from backend.domain.software_distribution.operations import ActiveOperationsSnapshot
from backend.infrastructure.db.repositories.settings.base import SettingsRepositoryBase
from backend.shared.ids import new_uuid


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class StationUpdateSettings:
    workstation_key: str
    branch_id: str
    channel: str
    maintenance_window: str
    installed_version: str
    schema_version: int | None
    install_profile: str
    last_seen_at: str
    last_check_at: str
    last_check_result: str


class SqliteStationUpdateRepository(SettingsRepositoryBase):
    def get(self, workstation_key: str) -> StationUpdateSettings | None:
        row = self._query_one(
            "SELECT * FROM software_station_settings WHERE workstation_key = ?",
            (workstation_key,))
        if row is None:
            return None
        return StationUpdateSettings(
            workstation_key=row["workstation_key"], branch_id=row.get("branch_id") or "",
            channel=row.get("channel") or "stable",
            maintenance_window=row.get("maintenance_window") or "",
            installed_version=row.get("installed_version") or "",
            schema_version=row.get("schema_version"),
            install_profile=row.get("install_profile") or "",
            last_seen_at=row.get("last_seen_at") or "",
            last_check_at=row.get("last_check_at") or "",
            last_check_result=row.get("last_check_result") or "",
        )

    def record_start(
        self, *, workstation_key: str, branch_id: str, installed_version: str,
        schema_version: int | None, install_profile: str, enabled_capabilities: str,
        default_channel: str,
    ) -> None:
        """Version inventory: what this station runs, refreshed at each start.
        The channel is only seeded (from the installer) the first time."""
        now = _now_iso()
        self._execute(
            "INSERT INTO software_station_settings (id, workstation_key, branch_id, channel,"
            " installed_version, schema_version, install_profile, enabled_capabilities,"
            " last_seen_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(workstation_key) DO UPDATE SET"
            " branch_id=COALESCE(NULLIF(excluded.branch_id,''), software_station_settings.branch_id),"
            " installed_version=excluded.installed_version,"
            " schema_version=excluded.schema_version,"
            " install_profile=excluded.install_profile,"
            " enabled_capabilities=excluded.enabled_capabilities,"
            " last_seen_at=excluded.last_seen_at",
            (new_uuid(), workstation_key, branch_id, default_channel, installed_version,
             schema_version, install_profile, enabled_capabilities, now, now))

    def set_channel(self, workstation_key: str, channel: str, *, user_id: str) -> None:
        self._execute(
            "UPDATE software_station_settings SET channel=?, updated_by=?, updated_at=?"
            " WHERE workstation_key=?", (channel, user_id, _now_iso(), workstation_key))

    def set_maintenance_window(self, workstation_key: str, window: str | None, *,
                               user_id: str) -> None:
        self._execute(
            "UPDATE software_station_settings SET maintenance_window=?, updated_by=?,"
            " updated_at=? WHERE workstation_key=?",
            (window, user_id, _now_iso(), workstation_key))

    def set_last_check(self, workstation_key: str, result: str) -> None:
        self._execute(
            "UPDATE software_station_settings SET last_check_at=?, last_check_result=?"
            " WHERE workstation_key=?", (_now_iso(), result[:500], workstation_key))

    def record_event(
        self, *, workstation_key: str, event_type: str, operation_id: str | None = None,
        job_id: str | None = None, branch_id: str = "", from_version: str = "",
        to_version: str = "", channel: str = "", detail: str = "", actor_user_id: str = "",
        occurred_at: str | None = None,
    ) -> str:
        event_id = new_uuid()
        self._execute(
            "INSERT INTO software_update_events (id, operation_id, job_id, workstation_key,"
            " branch_id, event_type, from_version, to_version, channel, detail, actor_user_id,"
            " occurred_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (event_id, operation_id or new_uuid(), job_id, workstation_key, branch_id,
             event_type, from_version, to_version, channel, detail[:2000], actor_user_id,
             occurred_at or _now_iso()))
        return event_id

    def has_event(self, job_id: str, event_type: str) -> bool:
        return self._query_one(
            "SELECT 1 AS hit FROM software_update_events WHERE job_id=? AND event_type=?",
            (job_id, event_type)) is not None

    def list_recent_events(self, limit: int) -> list[dict]:
        """Every station's trail, newest first (the per-station inventory)."""
        return self._query(
            "SELECT id, workstation_key, event_type, from_version, to_version, channel, detail,"
            " occurred_at FROM software_update_events ORDER BY occurred_at DESC LIMIT ?",
            (int(limit),))

    def list_events(self, workstation_key: str, limit: int) -> list[dict]:
        return self._query(
            "SELECT event_type, from_version, to_version, channel, detail, actor_user_id,"
            " occurred_at FROM software_update_events WHERE workstation_key=?"
            " ORDER BY occurred_at DESC LIMIT ?", (workstation_key, int(limit)))


#: Statuses of the canonical POS/cash tables that mean "someone is in the
#: middle of it". Copied from the domain enums
#: (`backend/domain/sales/enums.py::SaleStatus`,
#: `backend/domain/cash_register/enums.py::CashShiftStatus`).
_PAYMENT_PENDING_STATUSES = ("CHECKOUT_PENDING", "PAYMENT_PENDING")
_CASH_CUT_STATUSES = ("PENDING_COUNT", "COUNTING", "COUNTED", "PENDING_REVIEW", "CLOSING")
_OUTBOX_PENDING_STATUSES = ("PENDING", "RETRY", "QUEUED", "FAILED")


class SqliteActiveOperationsProbe(SettingsRepositoryBase):
    """Counts operations an update must not interrupt.

    A sale counts as "in capture" when it is ACTIVE, has at least one line
    and was opened within `recent_hours` — tickets abandoned days ago (the
    real database has dozens) must not block updates forever. An OPEN cash
    shift does not block: shifts stay open all day and survive a restart.
    """

    def __init__(self, connection, *, recent_hours: int = 12) -> None:
        super().__init__(connection)
        self._recent_hours = recent_hours

    def snapshot(self) -> ActiveOperationsSnapshot:
        since = (datetime.now(timezone.utc) - timedelta(hours=self._recent_hours)).isoformat(
            timespec="seconds")
        sales_in_capture = payments = cuts = outbox = 0
        if self._has_table("sales"):
            if self._has_table("sale_lines"):
                sales_in_capture = self._count(
                    "SELECT COUNT(*) FROM sales s WHERE s.status='ACTIVE' AND s.created_at>=?"
                    " AND EXISTS (SELECT 1 FROM sale_lines l WHERE l.sale_id=s.id)", (since,))
            payments = self._count(
                "SELECT COUNT(*) FROM sales WHERE status IN (?,?) AND created_at>=?",
                (*_PAYMENT_PENDING_STATUSES, since))
        if self._has_table("cash_shifts"):
            marks = ",".join("?" * len(_CASH_CUT_STATUSES))
            cuts = self._count(
                f"SELECT COUNT(*) FROM cash_shifts WHERE status IN ({marks})", _CASH_CUT_STATUSES)
        for table in self._outbox_tables():
            marks = ",".join("?" * len(_OUTBOX_PENDING_STATUSES))
            outbox += self._count(
                f'SELECT COUNT(*) FROM "{table}" WHERE upper(status) IN ({marks})',
                _OUTBOX_PENDING_STATUSES)
        return ActiveOperationsSnapshot(
            sales_in_capture=sales_in_capture, payments_pending=payments,
            cash_cuts_in_progress=cuts, pending_outbox_messages=outbox)

    def _has_table(self, name: str) -> bool:
        return self._query_one(
            "SELECT 1 AS hit FROM sqlite_master WHERE type='table' AND name=?", (name,)) is not None

    def _outbox_tables(self) -> list[str]:
        tables = [row["name"] for row in self._query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%outbox%'")]
        result = []
        for table in tables:
            columns = {row[1] for row in self._conn.execute(f'PRAGMA table_info("{table}")')}
            if "status" in columns:
                result.append(table)
        return result

    def _count(self, sql: str, params: tuple) -> int:
        row = self._conn.execute(sql, params).fetchone()
        return int(row[0] or 0) if row else 0
