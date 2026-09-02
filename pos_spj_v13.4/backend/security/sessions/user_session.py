"""UserSession — SHELL-1 security foundation.

Immutable session record. Never carries the password or password hash —
only enough to identify who's logged in, where, and until when.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class SessionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    LOCKED = "LOCKED"
    TERMINATED = "TERMINATED"


@dataclass(frozen=True)
class UserSession:
    session_id: str
    user_id: str
    company_id: str
    branch_id: str
    workstation_id: str
    authentication_method: str
    created_at: datetime
    last_activity_at: datetime
    expires_at: datetime
    status: SessionStatus = SessionStatus.ACTIVE

    def is_active(self, *, now: datetime | None = None) -> bool:
        from datetime import timezone

        now = now or datetime.now(timezone.utc)
        return self.status is SessionStatus.ACTIVE and now < self.expires_at

    def with_status(self, status: SessionStatus) -> "UserSession":
        return UserSession(
            session_id=self.session_id,
            user_id=self.user_id,
            company_id=self.company_id,
            branch_id=self.branch_id,
            workstation_id=self.workstation_id,
            authentication_method=self.authentication_method,
            created_at=self.created_at,
            last_activity_at=self.last_activity_at,
            expires_at=self.expires_at,
            status=status,
        )

    def touched(self, *, at: datetime) -> "UserSession":
        return UserSession(
            session_id=self.session_id,
            user_id=self.user_id,
            company_id=self.company_id,
            branch_id=self.branch_id,
            workstation_id=self.workstation_id,
            authentication_method=self.authentication_method,
            created_at=self.created_at,
            last_activity_at=at,
            expires_at=self.expires_at,
            status=self.status,
        )
