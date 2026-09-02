"""RecoveryCodeRepository — SHELL-2 security foundation.

Real SQLite persistence against `installation_recovery_codes` (created by
migration 206) — a recovery kit is meant to still work months after it was
generated, so unlike SHELL-1's deferred choices this needs to survive
restarts from day one, same reasoning as `InstallationRepository`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from backend.security.provisioning.recovery_code import RecoveryCode, RecoveryCodeStatus


@runtime_checkable
class RecoveryCodeRepository(Protocol):
    def save(self, code: RecoveryCode) -> None: ...

    def find_by_hash(self, code_hash: str) -> RecoveryCode | None: ...

    def find_active_for_installation(self, installation_id: str) -> list[RecoveryCode]: ...

    def replace(self, code: RecoveryCode) -> None: ...


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _format_dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class SqliteRecoveryCodeRepository:
    def __init__(self, conn) -> None:
        self._conn = conn

    def save(self, code: RecoveryCode) -> None:
        self._conn.execute(
            "INSERT INTO installation_recovery_codes "
            "(id, installation_id, code_hash, status, created_at, used_at) "
            "VALUES (?,?,?,?,?,?)",
            (
                code.id, code.installation_id, code.code_hash, code.status.value,
                _format_dt(code.created_at), _format_dt(code.used_at),
            ),
        )

    def find_by_hash(self, code_hash: str) -> RecoveryCode | None:
        row = self._conn.execute(
            "SELECT id, installation_id, code_hash, status, created_at, used_at "
            "FROM installation_recovery_codes WHERE code_hash = ?",
            (code_hash,),
        ).fetchone()
        return self._row_to_code(row) if row else None

    def find_active_for_installation(self, installation_id: str) -> list[RecoveryCode]:
        rows = self._conn.execute(
            "SELECT id, installation_id, code_hash, status, created_at, used_at "
            "FROM installation_recovery_codes WHERE installation_id = ? AND status = 'ACTIVE'",
            (installation_id,),
        ).fetchall()
        return [self._row_to_code(row) for row in rows]

    def replace(self, code: RecoveryCode) -> None:
        self._conn.execute(
            "UPDATE installation_recovery_codes SET status = ?, used_at = ? WHERE id = ?",
            (code.status.value, _format_dt(code.used_at), code.id),
        )

    @staticmethod
    def _row_to_code(row) -> RecoveryCode:
        return RecoveryCode(
            id=row["id"], installation_id=row["installation_id"], code_hash=row["code_hash"],
            status=RecoveryCodeStatus(row["status"]),
            created_at=_parse_dt(row["created_at"]), used_at=_parse_dt(row["used_at"]),
        )


class InMemoryRecoveryCodeRepository:
    def __init__(self) -> None:
        self._by_hash: dict[str, RecoveryCode] = {}

    def save(self, code: RecoveryCode) -> None:
        self._by_hash[code.code_hash] = code

    def find_by_hash(self, code_hash: str) -> RecoveryCode | None:
        return self._by_hash.get(code_hash)

    def find_active_for_installation(self, installation_id: str) -> list[RecoveryCode]:
        return [
            c for c in self._by_hash.values()
            if c.installation_id == installation_id and c.status is RecoveryCodeStatus.ACTIVE
        ]

    def replace(self, code: RecoveryCode) -> None:
        self._by_hash[code.code_hash] = code
