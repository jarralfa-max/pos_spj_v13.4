"""Persistencia de `user_role_assignments` (migración 353; auditoría enterprise,
Fase 2). Nunca confirma: la frontera transaccional es de quien llama."""

from __future__ import annotations

from datetime import date
from typing import Any

from backend.domain.organization.role_assignment import (
    AssignmentStatus,
    RoleAssignment,
    ScopeType,
)
from backend.infrastructure.db.repositories.security.base import SecurityRepositoryBase
from backend.infrastructure.db.transaction import TransactionalUnitOfWork

_COLS = ("id, user_id, role_id, scope_type, scope_id, valid_from, valid_until, status, reason,"
         " granted_by, created_at, revoked_at, revoked_by, revoke_reason")


def _d(valor) -> date | None:
    return date.fromisoformat(str(valor)[:10]) if valor else None


def _row(r: dict) -> RoleAssignment:
    return RoleAssignment(
        id=r["id"], user_id=r["user_id"], role_id=r["role_id"],
        scope_type=ScopeType(r["scope_type"]), scope_id=r["scope_id"], reason=r["reason"],
        valid_from=_d(r["valid_from"]), valid_until=_d(r["valid_until"]),
        status=AssignmentStatus(r["status"]), granted_by=r["granted_by"],
        created_at=r["created_at"], revoked_at=r["revoked_at"], revoked_by=r["revoked_by"],
        revoke_reason=r["revoke_reason"])


class SqliteRoleAssignmentRepository(SecurityRepositoryBase):
    def available(self) -> bool:
        return self._table_exists("user_role_assignments")

    def get(self, assignment_id: str) -> RoleAssignment | None:
        fila = self._query_one(f"SELECT {_COLS} FROM user_role_assignments WHERE id=?",
                               (str(assignment_id),))
        return _row(fila) if fila else None

    def active_duplicate(self, a: RoleAssignment) -> bool:
        return self._query_one(
            "SELECT 1 AS x FROM user_role_assignments WHERE user_id=? AND role_id=?"
            " AND scope_type=? AND scope_id=? AND status='ACTIVE' AND id<>?",
            (a.user_id, a.role_id, a.scope_type.value, a.scope_id, a.id)) is not None

    def save(self, a: RoleAssignment) -> None:
        self._conn.execute(
            f"INSERT INTO user_role_assignments ({_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET status=excluded.status,"
            " revoked_at=excluded.revoked_at, revoked_by=excluded.revoked_by,"
            " revoke_reason=excluded.revoke_reason",
            (a.id, a.user_id, a.role_id, a.scope_type.value, a.scope_id,
             a.valid_from.isoformat() if a.valid_from else None,
             a.valid_until.isoformat() if a.valid_until else None, a.status.value, a.reason,
             a.granted_by, a.created_at, a.revoked_at, a.revoked_by, a.revoke_reason))

    def list_for_user(self, user_id: str) -> list[dict]:
        """Filas para la pantalla: rol y ámbito con nombre, vigentes primero."""
        unidades = self._table_exists("org_units")
        ambito = ("CASE a.scope_type WHEN 'COMPANY' THEN 'Toda la empresa'"
                  " ELSE COALESCE(u.name, a.scope_id) END" if unidades else
                  "CASE a.scope_type WHEN 'COMPANY' THEN 'Toda la empresa' ELSE a.scope_id END")
        union = " LEFT JOIN org_units u ON u.id = a.scope_id" if unidades else ""
        return self._query(
            f"SELECT a.id, a.role_id, r.nombre AS role_name, a.scope_type, a.scope_id,"
            f" {ambito} AS scope_name, a.valid_from, a.valid_until, a.status, a.reason,"
            f" a.granted_by, a.created_at, a.revoked_at, a.revoke_reason"
            f" FROM user_role_assignments a JOIN roles r ON r.id = a.role_id{union}"
            " WHERE a.user_id=? ORDER BY a.status, a.created_at", (str(user_id),))

    def roles(self) -> list[dict]:
        return self._query("SELECT id, nombre FROM roles ORDER BY nombre")

    def role(self, role_id: str) -> dict | None:
        return self._query_one("SELECT id, nombre FROM roles WHERE id=?", (str(role_id),))

    def user_exists(self, user_id: str) -> bool:
        return self._query_one("SELECT 1 AS x FROM usuarios WHERE id=?",
                               (str(user_id),)) is not None


class RoleAssignmentUnitOfWork(TransactionalUnitOfWork):
    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.assignments = SqliteRoleAssignmentRepository(connection)
        self._completed = False


__all__ = ["RoleAssignmentUnitOfWork", "SqliteRoleAssignmentRepository"]
