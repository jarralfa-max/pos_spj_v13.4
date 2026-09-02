"""AuthenticateUserUseCase — SHELL-7.

The whole point of SHELL-7's "Lockout" and password-rehash stories, wired
into one flow:

  1. Check the submitted username isn't currently locked out — *before*
     looking up whether it's a real account, so lockout behavior can't be
     used to enumerate valid usernames.
  2. Look up credentials; a missing or inactive account fails exactly the
     same generic way an existing one with a wrong password does.
  3. Verify via `MultiSchemePasswordVerifier` (Argon2id primary, bcrypt
     legacy — see that module's docstring for why bcrypt has to stay
     supported here).
  4. On a legacy-scheme success, silently rehash to the primary scheme.
  5. Record the attempt either way; a failure that pushes the account over
     the lockout threshold emits `ACCOUNT_LOCKED` in addition to
     `USER_AUTHENTICATION_FAILED`.
  6. On success, open a `UserSession` via SHELL-1's `SessionManager`.

Building `ApplicationContext` from the result is `AuthenticationCoordinator`'s
job, not this use case's — this only proves who the user is and starts
their session.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from backend.security.audit.security_events import (
    ACCOUNT_LOCKED,
    USER_AUTHENTICATION_FAILED,
    USER_AUTHENTICATION_SUCCEEDED,
)
from backend.security.authentication.authentication_attempt_repository import AuthenticationAttemptRepository
from backend.security.authentication.errors import AuthenticationFailedError
from backend.security.authentication.user_credentials import UserCredentials, UserCredentialsRepository
from backend.security.credentials.password_verification import MultiSchemePasswordVerifier
from backend.security.sessions.account_lockout_policy import AccountLockoutPolicy
from backend.security.sessions.authentication_attempt import AuthenticationAttempt
from backend.security.sessions.session_manager import SessionManager
from backend.security.sessions.user_session import UserSession

AuditSink = Callable[[str, dict], None]

_GENERIC_FAILURE_MESSAGE = "Usuario o contraseña incorrectos."


@dataclass(frozen=True)
class AuthenticationResult:
    credentials: UserCredentials
    session: UserSession


class AuthenticateUserUseCase:
    def __init__(
        self,
        *,
        credentials_repository: UserCredentialsRepository,
        attempt_repository: AuthenticationAttemptRepository,
        password_verifier: MultiSchemePasswordVerifier,
        lockout_policy: AccountLockoutPolicy,
        session_manager: SessionManager,
        audit_sink: Optional[AuditSink] = None,
    ) -> None:
        self._credentials = credentials_repository
        self._attempts = attempt_repository
        self._verifier = password_verifier
        self._lockout = lockout_policy
        self._sessions = session_manager
        self._audit = audit_sink or (lambda event, payload: None)

    def execute(
        self,
        *,
        username: str,
        password: str,
        workstation_id: str = "",
        company_id: str = "",
        now: datetime | None = None,
    ) -> AuthenticationResult:
        now = now or datetime.now(timezone.utc)
        username = (username or "").strip()
        if not username or not password:
            raise AuthenticationFailedError(_GENERIC_FAILURE_MESSAGE)

        self._lockout.require_not_locked_out(
            self._attempts.recent_for_user(username), now=now,
        )

        credentials = self._credentials.find_by_username(username)
        if credentials is None or not credentials.active:
            self._record_failure(username, workstation_id, "unknown_or_inactive_account", now)
            raise AuthenticationFailedError(_GENERIC_FAILURE_MESSAGE)

        verification = self._verifier.verify(password, credentials.password_hash)
        if not verification.valid:
            self._record_failure(username, workstation_id, "invalid_password", now)
            raise AuthenticationFailedError(_GENERIC_FAILURE_MESSAGE)

        if verification.needs_rehash:
            self._credentials.update_password_hash(credentials.id, self._verifier.hash(password))

        self._attempts.record(AuthenticationAttempt.succeeded(
            username, workstation_id=workstation_id, occurred_at=now,
        ))
        self._audit(USER_AUTHENTICATION_SUCCEEDED, {"user_id": credentials.id, "username": username})

        session = self._sessions.create_session(
            user_id=credentials.id, company_id=company_id, branch_id=credentials.branch_id,
            workstation_id=workstation_id, authentication_method="password", now=now,
        )
        return AuthenticationResult(credentials=credentials, session=session)

    def _record_failure(self, username: str, workstation_id: str, reason: str, now: datetime) -> None:
        self._attempts.record(AuthenticationAttempt.failure(
            username, workstation_id=workstation_id, reason=reason, occurred_at=now,
        ))
        self._audit(USER_AUTHENTICATION_FAILED, {"username": username, "reason": reason})

        recent = self._attempts.recent_for_user(username)
        if self._lockout.is_locked_out(recent, now=now):
            self._audit(ACCOUNT_LOCKED, {"username": username})
