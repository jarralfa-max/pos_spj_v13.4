"""SessionRepository port — SHELL-1 security foundation.

Same deferred-persistence pattern as `RecoveryTokenRepository`: the real
adapter (a migration-defined `user_sessions` table) is a later-phase
concern. This module defines the contract plus an in-memory reference
implementation for tests and for composing `SessionManager` today.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.security.sessions.user_session import UserSession


@runtime_checkable
class SessionRepository(Protocol):
    def save(self, session: UserSession) -> None: ...

    def find_by_id(self, session_id: str) -> UserSession | None: ...

    def find_active_for_user(self, user_id: str) -> list[UserSession]: ...

    def replace(self, session: UserSession) -> None:
        """Persist a mutated session (status change, touch, etc.)."""
        ...


class InMemorySessionRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, UserSession] = {}

    def save(self, session: UserSession) -> None:
        self._by_id[session.session_id] = session

    def find_by_id(self, session_id: str) -> UserSession | None:
        return self._by_id.get(session_id)

    def find_active_for_user(self, user_id: str) -> list[UserSession]:
        from backend.security.sessions.user_session import SessionStatus

        return [
            s for s in self._by_id.values()
            if s.user_id == user_id and s.status is SessionStatus.ACTIVE
        ]

    def replace(self, session: UserSession) -> None:
        self._by_id[session.session_id] = session
