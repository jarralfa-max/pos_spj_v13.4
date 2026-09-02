"""SessionManager — SHELL-1 security foundation.

Owns session lifecycle transitions (create → touch → expire/revoke/
terminate). Delegates persistence to a `SessionRepository` port so this
class stays testable without a database.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from backend.security.audit.security_events import (
    USER_SESSION_CREATED as EVENT_USER_SESSION_CREATED,
    USER_SESSION_EXPIRED as EVENT_USER_SESSION_EXPIRED,
    USER_SESSION_REVOKED as EVENT_USER_SESSION_REVOKED,
)
from backend.security.sessions.session_repository import SessionRepository
from backend.security.sessions.user_session import SessionStatus, UserSession
from backend.shared.ids import new_uuid

AuditSink = Callable[[str, dict], None]

DEFAULT_SESSION_TTL_SECONDS = 8 * 60 * 60  # one shift


class SessionManager:
    def __init__(
        self,
        *,
        session_repository: SessionRepository,
        default_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
        audit_sink: Optional[AuditSink] = None,
    ) -> None:
        self._sessions = session_repository
        self._default_ttl_seconds = default_ttl_seconds
        self._audit = audit_sink or (lambda event, payload: None)

    def create_session(
        self,
        *,
        user_id: str,
        company_id: str,
        branch_id: str,
        workstation_id: str,
        authentication_method: str,
        ttl_seconds: int | None = None,
        now: datetime | None = None,
    ) -> UserSession:
        if not user_id:
            raise ValueError("user_id no puede estar vacío.")
        now = now or datetime.now(timezone.utc)
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl_seconds
        session = UserSession(
            session_id=new_uuid(),
            user_id=user_id,
            company_id=company_id or "",
            branch_id=branch_id or "",
            workstation_id=workstation_id or "",
            authentication_method=authentication_method or "password",
            created_at=now,
            last_activity_at=now,
            expires_at=now + timedelta(seconds=ttl),
            status=SessionStatus.ACTIVE,
        )
        self._sessions.save(session)
        self._audit(EVENT_USER_SESSION_CREATED, {"user_id": user_id, "session_id": session.session_id})
        return session

    def get_active_session(
        self, session_id: str, *, now: datetime | None = None
    ) -> UserSession | None:
        """Returns the session only if it is genuinely active right now.
        A session found past its `expires_at` is transitioned to EXPIRED as
        a side effect (lazy expiry) and this returns None."""
        now = now or datetime.now(timezone.utc)
        session = self._sessions.find_by_id(session_id)
        if session is None:
            return None
        if session.status is not SessionStatus.ACTIVE:
            return None
        if now >= session.expires_at:
            expired = session.with_status(SessionStatus.EXPIRED)
            self._sessions.replace(expired)
            self._audit(EVENT_USER_SESSION_EXPIRED, {"user_id": session.user_id, "session_id": session_id})
            return None
        return session

    def touch(self, session_id: str, *, now: datetime | None = None) -> UserSession | None:
        now = now or datetime.now(timezone.utc)
        session = self.get_active_session(session_id, now=now)
        if session is None:
            return None
        touched = session.touched(at=now)
        self._sessions.replace(touched)
        return touched

    def revoke(self, session_id: str, *, now: datetime | None = None) -> UserSession | None:
        session = self._sessions.find_by_id(session_id)
        if session is None:
            return None
        revoked = session.with_status(SessionStatus.REVOKED)
        self._sessions.replace(revoked)
        self._audit(EVENT_USER_SESSION_REVOKED, {"user_id": session.user_id, "session_id": session_id})
        return revoked

    def terminate_all_for_user(self, user_id: str, *, now: datetime | None = None) -> list[UserSession]:
        terminated = []
        for session in self._sessions.find_active_for_user(user_id):
            updated = session.with_status(SessionStatus.TERMINATED)
            self._sessions.replace(updated)
            terminated.append(updated)
        return terminated
