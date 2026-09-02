"""CreateInitialOwnerUseCase — SHELL-2 security foundation.

Creates the first user account for a freshly provisioned installation, with
the `system_owner` role (full access — see migration 206). The account is
built entirely from data captured in `owner_account_page` at wizard time;
nothing about it pre-exists in code or migrations, per the born-clean rule
("no usuarios predeterminados").

Takes a live `conn` directly (matching this codebase's existing repository
convention — see `security/auth.py::crear_usuario`) rather than a new
repository abstraction, since inserting a row is not a schema change and
`ProvisionInstallationUseCase` needs this to run inside its own transaction.

IMPORTANT: pass a `BcryptPasswordHasher`, not `Argon2idPasswordHasher`, until
SHELL-7's AuthenticationCoordinator cuts the live login path over to
Argon2id — `core/services/auth_service.py::AuthService` only verifies
bcrypt hashes today, so an Argon2id hash here would create an owner account
that cannot actually log in. See `password_hasher.py`'s module docstring.
"""
from __future__ import annotations

from backend.security.credentials.password_hasher import PasswordHasher
from backend.security.credentials.password_policy import PasswordPolicy
from backend.shared.ids import SYSTEM_ROLE_UUIDS, new_uuid

OWNER_ROLE_NAME = "system_owner"


class OwnerUsernameTakenError(ValueError):
    """The requested username is already in use — cannot happen on a truly
    fresh install, but guards against a wizard retry after a partial
    failure."""


class CreateInitialOwnerUseCase:
    def __init__(
        self, conn, *, password_hasher: PasswordHasher, password_policy: PasswordPolicy,
    ) -> None:
        self._conn = conn
        self._hasher = password_hasher
        self._policy = password_policy

    def execute(
        self,
        *,
        username: str,
        password: str,
        full_name: str,
        branch_id: str,
        recovery_contact: str = "",
    ) -> str:
        username = (username or "").strip()
        full_name = (full_name or "").strip()
        branch_id = (branch_id or "").strip()
        if not username:
            raise ValueError("username no puede estar vacío.")
        if not full_name:
            raise ValueError("full_name no puede estar vacío.")
        if not branch_id:
            raise ValueError("branch_id no puede estar vacío.")

        existing = self._conn.execute(
            "SELECT 1 FROM usuarios WHERE usuario = ?", (username,)
        ).fetchone()
        if existing:
            raise OwnerUsernameTakenError(f"El usuario '{username}' ya existe.")

        self._policy.validate(password, username=username)
        password_hash = self._hasher.hash(password)

        user_id = new_uuid()
        self._conn.execute(
            "INSERT INTO usuarios "
            "(id, nombre, usuario, password_hash, rol, sucursal_id, activo, recovery_contact) "
            "VALUES (?,?,?,?,?,?,1,?)",
            (user_id, full_name, username, password_hash, OWNER_ROLE_NAME, branch_id,
             recovery_contact.strip() if recovery_contact else None),
        )
        # Permisos: vía RBAC por rol (rol_permisos, sembrado en la migración
        # 206 para 'system_owner' con acceso total) — no una tabla
        # usuario_modulos, que no forma parte del esquema vigente.
        return user_id

    @staticmethod
    def owner_role_id() -> str:
        return SYSTEM_ROLE_UUIDS[OWNER_ROLE_NAME]
