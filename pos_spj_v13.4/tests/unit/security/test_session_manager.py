from datetime import datetime, timedelta, timezone

import pytest

from backend.security.sessions.session_manager import SessionManager
from backend.security.sessions.session_repository import InMemorySessionRepository
from backend.security.sessions.user_session import SessionStatus

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def manager() -> SessionManager:
    return SessionManager(session_repository=InMemorySessionRepository(), default_ttl_seconds=3600)


def _create(manager, **overrides):
    kwargs = dict(
        user_id="user-1", company_id="company-1", branch_id="branch-1",
        workstation_id="ws-1", authentication_method="password", now=T0,
    )
    kwargs.update(overrides)
    return manager.create_session(**kwargs)


def test_create_session_is_active(manager):
    session = _create(manager)
    assert session.status is SessionStatus.ACTIVE
    assert session.is_active(now=T0 + timedelta(seconds=1))


def test_create_session_never_carries_password_fields(manager):
    session = _create(manager)
    assert not hasattr(session, "password")
    assert not hasattr(session, "password_hash")


def test_get_active_session_returns_session_within_ttl(manager):
    session = _create(manager)
    fetched = manager.get_active_session(session.session_id, now=T0 + timedelta(minutes=30))
    assert fetched is not None
    assert fetched.session_id == session.session_id


def test_get_active_session_returns_none_after_expiry(manager):
    session = _create(manager)
    fetched = manager.get_active_session(session.session_id, now=T0 + timedelta(hours=2))
    assert fetched is None


def test_get_active_session_returns_none_for_unknown_id(manager):
    assert manager.get_active_session("does-not-exist", now=T0) is None


def test_touch_updates_last_activity(manager):
    session = _create(manager)
    touched = manager.touch(session.session_id, now=T0 + timedelta(minutes=10))
    assert touched.last_activity_at == T0 + timedelta(minutes=10)
    assert touched.created_at == T0


def test_touch_on_expired_session_returns_none(manager):
    session = _create(manager)
    assert manager.touch(session.session_id, now=T0 + timedelta(hours=2)) is None


def test_revoke_marks_session_revoked_and_blocks_further_use(manager):
    session = _create(manager)
    revoked = manager.revoke(session.session_id, now=T0 + timedelta(minutes=1))
    assert revoked.status is SessionStatus.REVOKED
    assert manager.get_active_session(session.session_id, now=T0 + timedelta(minutes=2)) is None


def test_revoke_unknown_session_returns_none(manager):
    assert manager.revoke("does-not-exist") is None


def test_terminate_all_for_user_only_affects_that_user(manager):
    session_a = _create(manager, user_id="user-1")
    session_b = _create(manager, user_id="user-2")

    terminated = manager.terminate_all_for_user("user-1", now=T0 + timedelta(minutes=1))

    assert len(terminated) == 1
    assert terminated[0].session_id == session_a.session_id
    assert manager.get_active_session(session_a.session_id, now=T0 + timedelta(minutes=2)) is None
    assert manager.get_active_session(session_b.session_id, now=T0 + timedelta(minutes=2)) is not None


def test_create_session_rejects_empty_user_id(manager):
    with pytest.raises(ValueError):
        manager.create_session(
            user_id="", company_id="c", branch_id="b", workstation_id="w",
            authentication_method="password",
        )


def test_audit_sink_receives_canonical_session_events():
    events = []
    manager = SessionManager(
        session_repository=InMemorySessionRepository(),
        audit_sink=lambda event, payload: events.append((event, payload)),
    )
    session = _create(manager)
    manager.revoke(session.session_id, now=T0 + timedelta(minutes=1))

    event_names = [e for e, _ in events]
    assert "USER_SESSION_CREATED" in event_names
    assert "USER_SESSION_REVOKED" in event_names
