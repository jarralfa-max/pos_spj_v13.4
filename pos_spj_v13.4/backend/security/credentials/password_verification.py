"""MultiSchemePasswordVerifier — SHELL-7.

`Argon2idPasswordHasher.verify()` only recognizes `$argon2id$` hashes — it
returns False on a bcrypt hash, it doesn't fall back. Every account that
exists today (the seeded admin/demo users, and every owner account
`InitialSetupWizard` creates via `BcryptPasswordHasher`, per SHELL-2) is
bcrypt-hashed. A verifier that only tried Argon2id would reject 100% of
real accounts — this is the piece that makes SHELL-7's login path actually
work against them while still treating Argon2id as the target scheme.

Verification order: try `primary` (Argon2id) first; if the hash isn't in
that scheme, fall through `legacy` hashers in order. A successful legacy
match reports `needs_rehash=True` unconditionally — a bcrypt verification
always warrants migrating to the primary scheme, regardless of what
`legacy_hasher.needs_rehash()` itself would say (bcrypt hashers report
their own scheme as never needing rehash, which is correct in isolation but
irrelevant here). `hash()` always produces a primary-scheme hash — this is
what `AuthenticateUserUseCase` calls to actually perform the migration on a
successful legacy login.
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.security.credentials.password_hasher import PasswordHasher


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    needs_rehash: bool


class MultiSchemePasswordVerifier:
    def __init__(self, *, primary: PasswordHasher, legacy: tuple[PasswordHasher, ...] = ()) -> None:
        self._primary = primary
        self._legacy = tuple(legacy)

    def verify(self, password: str, hashed: str) -> VerificationResult:
        if self._primary.verify(password, hashed):
            return VerificationResult(valid=True, needs_rehash=self._primary.needs_rehash(hashed))
        for hasher in self._legacy:
            if hasher.verify(password, hashed):
                return VerificationResult(valid=True, needs_rehash=True)
        return VerificationResult(valid=False, needs_rehash=False)

    def hash(self, password: str) -> str:
        """Always produces a hash in the primary (target) scheme."""
        return self._primary.hash(password)
