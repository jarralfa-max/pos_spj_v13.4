"""UserCredentialsRepository — SHELL-7.

Read access to `usuarios` for the new authentication path, plus the one
write it needs: persisting a rehashed `password_hash` after a successful
legacy-scheme login (`MultiSchemePasswordVerifier`'s migration story).
Deliberately narrow — no create/delete/permission-management here; account
creation stays `CreateInitialOwnerUseCase`'s job (SHELL-2), and RBAC stays
`PermissionQueryService`'s (existing, untouched).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class UserCredentials:
    id: str
    username: str
    password_hash: str
    full_name: str
    role: str
    branch_id: str
    active: bool
    recovery_contact: str = ""


@runtime_checkable
class UserCredentialsRepository(Protocol):
    def find_by_username(self, username: str) -> UserCredentials | None: ...

    def find_by_id(self, user_id: str) -> UserCredentials | None: ...

    def update_password_hash(self, user_id: str, new_hash: str) -> None: ...


class SqliteUserCredentialsRepository:
    def __init__(self, conn) -> None:
        self._conn = conn

    def find_by_username(self, username: str) -> UserCredentials | None:
        row = self._conn.execute(
            "SELECT id, usuario, password_hash, nombre, rol, sucursal_id, activo, "
            "recovery_contact FROM usuarios WHERE usuario = ?",
            (username,),
        ).fetchone()
        return self._row_to_credentials(row) if row else None

    def find_by_id(self, user_id: str) -> UserCredentials | None:
        row = self._conn.execute(
            "SELECT id, usuario, password_hash, nombre, rol, sucursal_id, activo, "
            "recovery_contact FROM usuarios WHERE id = ?",
            (user_id,),
        ).fetchone()
        return self._row_to_credentials(row) if row else None

    def update_password_hash(self, user_id: str, new_hash: str) -> None:
        self._conn.execute(
            "UPDATE usuarios SET password_hash = ? WHERE id = ?", (new_hash, user_id),
        )

    @staticmethod
    def _row_to_credentials(row) -> UserCredentials:
        return UserCredentials(
            id=row["id"], username=row["usuario"], password_hash=row["password_hash"],
            full_name=row["nombre"] or "", role=str(row["rol"] or "").lower(),
            branch_id=row["sucursal_id"] or "", active=bool(row["activo"]),
            recovery_contact=row["recovery_contact"] or "",
        )
