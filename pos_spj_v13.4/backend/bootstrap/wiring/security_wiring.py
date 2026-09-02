"""SecurityModuleProvider — SHELL-5 §14.

Wires the SHELL-1 security primitives: `PasswordPolicy`, `PasswordHasher`
(canonical = `Argon2idPasswordHasher` — the target algorithm; see
`password_hasher.py`'s module docstring for why callers that must work
against *today's* live login path, like `CreateInitialOwnerUseCase`, still
construct `BcryptPasswordHasher` directly instead of resolving this
registration — that cutover is SHELL-7's job), and `AccountLockoutPolicy`,
which is deliberately wired to *read its thresholds from* the registered
`PasswordPolicy` rather than hardcoding its own — one source of truth for
"how many failed attempts, how long the lockout" instead of two policy
objects that could drift apart.
"""
from __future__ import annotations

from backend.bootstrap.service_lifetime import Lifetime
from backend.bootstrap.service_registration import ServiceDependency
from backend.bootstrap.service_registry import ServiceRegistry
from backend.security.credentials.password_hasher import Argon2idPasswordHasher, PasswordHasher
from backend.security.credentials.password_policy import PasswordPolicy
from backend.security.sessions.account_lockout_policy import AccountLockoutPolicy


def _build_lockout_policy(resolver):
    policy: PasswordPolicy = resolver.resolve(PasswordPolicy)
    return AccountLockoutPolicy(
        failed_attempt_limit=policy.failed_attempt_limit,
        lockout_duration_seconds=policy.lockout_duration_seconds,
    )


class SecurityModuleProvider:
    def register(self, registry: ServiceRegistry) -> None:
        registry.register(
            PasswordPolicy,
            lambda resolver: PasswordPolicy(),
            lifetime=Lifetime.SINGLETON,
            canonical_for="PasswordPolicy",
        )
        registry.register(
            PasswordHasher,
            lambda resolver: Argon2idPasswordHasher(),
            lifetime=Lifetime.SINGLETON,
            canonical_for="PasswordHasher",
        )
        registry.register(
            AccountLockoutPolicy,
            _build_lockout_policy,
            lifetime=Lifetime.SINGLETON,
            dependencies=[ServiceDependency(key=PasswordPolicy)],
            canonical_for="AccountLockoutPolicy",
        )
