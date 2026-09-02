"""PasswordHasher port + implementations — SHELL-1 security foundation.

This hasher is intentionally single-purpose: it hashes and verifies. It does
not enforce password strength (see `password_policy.py`) and it never stores
or logs the plaintext password anywhere.

Two implementations exist:

- `Argon2idPasswordHasher` — the target algorithm per the master refactor
  plan (§28). This is what SHELL-7's AuthenticationCoordinator will cut the
  live login path over to.
- `BcryptPasswordHasher` — wraps the `bcrypt` library the live app
  (`core/services/auth_service.py::_check_password`,
  `security/auth.py::verify_password`) still verifies against *today*. Any
  account created by code that must be usable through the current login
  path (e.g. `CreateInitialOwnerUseCase` until SHELL-7 lands) must be hashed
  with this one, not Argon2id — otherwise the account is unusable through
  today's live verifier, even though it *is* a stronger hash. Once SHELL-7
  wires Argon2id as the live verifier, `Argon2idPasswordHasher.needs_rehash()`
  correctly reports `True` for these bcrypt hashes, which is what drives the
  automatic on-login rehash migration.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.security.credentials.errors import MissingPasswordHashingBackendError

try:
    from argon2 import PasswordHasher as _Argon2PasswordHasher
    from argon2 import Type as _Argon2Type
    from argon2.exceptions import InvalidHashError, VerifyMismatchError

    HAS_ARGON2 = True
except ImportError:  # pragma: no cover - exercised only when the dep is absent
    HAS_ARGON2 = False

try:
    import bcrypt as _bcrypt

    HAS_BCRYPT = True
except ImportError:  # pragma: no cover - exercised only when the dep is absent
    HAS_BCRYPT = False


@runtime_checkable
class PasswordHasher(Protocol):
    def hash(self, password: str) -> str:
        """Hash a plaintext password. Never returns or logs the plaintext."""
        ...

    def verify(self, password: str, hashed: str) -> bool:
        """Verify a plaintext password against a stored hash."""
        ...

    def needs_rehash(self, hashed: str) -> bool:
        """True when `hashed` was produced with weaker-than-current parameters
        (or a foreign algorithm) and should be regenerated on next successful
        login."""
        ...


class Argon2idPasswordHasher:
    """Argon2id-backed `PasswordHasher`.

    Parameters follow the OWASP-recommended Argon2id baseline for an
    interactive desktop login (not a high-throughput API): 19 MiB memory,
    2 iterations, single-lane parallelism. Tuned conservatively so a single
    login on modest hardware stays well under a second.
    """

    ALGORITHM_PREFIX = "$argon2id$"

    def __init__(
        self,
        *,
        time_cost: int = 2,
        memory_cost_kib: int = 19 * 1024,
        parallelism: int = 1,
        hash_len: int = 32,
        salt_len: int = 16,
    ) -> None:
        if not HAS_ARGON2:
            raise MissingPasswordHashingBackendError(
                "argon2-cffi no está instalado. Ejecute 'pip install argon2-cffi' "
                "— no existe una ruta alterna para hashear contraseñas."
            )
        self._hasher = _Argon2PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost_kib,
            parallelism=parallelism,
            hash_len=hash_len,
            salt_len=salt_len,
            type=_Argon2Type.ID,
        )

    def hash(self, password: str) -> str:
        if not password:
            raise ValueError("password no puede estar vacío.")
        return self._hasher.hash(password)

    def verify(self, password: str, hashed: str) -> bool:
        if not password or not hashed:
            return False
        try:
            return self._hasher.verify(hashed, password)
        except (VerifyMismatchError, InvalidHashError, ValueError):
            return False

    def needs_rehash(self, hashed: str) -> bool:
        if not hashed:
            return True
        try:
            return self._hasher.check_needs_rehash(hashed)
        except InvalidHashError:
            # Not an argon2id hash at all (legacy bcrypt/SHA-256) — always
            # needs migration to the current scheme.
            return True

    @staticmethod
    def is_argon2id_hash(value: str) -> bool:
        return bool(value) and value.startswith(Argon2idPasswordHasher.ALGORITHM_PREFIX)


class BcryptPasswordHasher:
    """Bcrypt-backed `PasswordHasher` — matches the current live verifier.

    See the module docstring: use this (not `Argon2idPasswordHasher`) for
    any account that must be able to log in through today's live app.
    """

    BCRYPT_PREFIXES = ("$2b$", "$2a$", "$2y$")

    def __init__(self, *, rounds: int = 12) -> None:
        if not HAS_BCRYPT:
            raise MissingPasswordHashingBackendError(
                "bcrypt no está instalado. Ejecute 'pip install bcrypt' — no existe "
                "una ruta alterna para hashear contraseñas."
            )
        self._rounds = rounds

    def hash(self, password: str) -> str:
        if not password:
            raise ValueError("password no puede estar vacío.")
        salt = _bcrypt.gensalt(self._rounds)
        return _bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    def verify(self, password: str, hashed: str) -> bool:
        if not password or not hashed or not hashed.startswith(self.BCRYPT_PREFIXES):
            return False
        try:
            return _bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except (ValueError, TypeError):
            return False

    def needs_rehash(self, hashed: str) -> bool:
        return not (hashed and hashed.startswith(self.BCRYPT_PREFIXES))
