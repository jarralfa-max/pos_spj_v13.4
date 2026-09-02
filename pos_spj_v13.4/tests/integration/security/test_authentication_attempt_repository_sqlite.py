from datetime import datetime, timedelta, timezone

from backend.security.authentication.authentication_attempt_repository import (
    SqliteAuthenticationAttemptRepository,
)
from backend.security.sessions.authentication_attempt import AuthenticationAttempt
from tests.integration._born_clean_db import make_db

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_record_and_retrieve_roundtrip():
    conn = make_db()
    repo = SqliteAuthenticationAttemptRepository(conn)
    repo.record(AuthenticationAttempt.failure("juan", workstation_id="ws-1", reason="bad_password", occurred_at=T0))
    conn.commit()

    attempts = repo.recent_for_user("juan")
    assert len(attempts) == 1
    assert attempts[0].success is False
    assert attempts[0].workstation_id == "ws-1"
    assert attempts[0].failure_reason == "bad_password"
    assert attempts[0].occurred_at == T0


def test_recent_for_user_returns_newest_first():
    conn = make_db()
    repo = SqliteAuthenticationAttemptRepository(conn)
    for i in range(3):
        repo.record(AuthenticationAttempt.failure("juan", occurred_at=T0 + timedelta(seconds=i)))
    conn.commit()

    attempts = repo.recent_for_user("juan")
    timestamps = [a.occurred_at for a in attempts]
    assert timestamps == sorted(timestamps, reverse=True)


def test_recent_for_user_respects_limit():
    conn = make_db()
    repo = SqliteAuthenticationAttemptRepository(conn)
    for i in range(10):
        repo.record(AuthenticationAttempt.failure("juan", occurred_at=T0 + timedelta(seconds=i)))
    conn.commit()

    assert len(repo.recent_for_user("juan", limit=3)) == 3


def test_attempts_are_scoped_per_user():
    conn = make_db()
    repo = SqliteAuthenticationAttemptRepository(conn)
    repo.record(AuthenticationAttempt.failure("juan", occurred_at=T0))
    repo.record(AuthenticationAttempt.failure("maria", occurred_at=T0))
    conn.commit()

    assert len(repo.recent_for_user("juan")) == 1
    assert len(repo.recent_for_user("maria")) == 1


def test_success_flag_persists_correctly():
    conn = make_db()
    repo = SqliteAuthenticationAttemptRepository(conn)
    repo.record(AuthenticationAttempt.succeeded("juan", workstation_id="ws-1", occurred_at=T0))
    conn.commit()

    attempts = repo.recent_for_user("juan")
    assert attempts[0].success is True
    assert attempts[0].failure_reason == ""


def test_no_attempts_returns_empty_list():
    conn = make_db()
    repo = SqliteAuthenticationAttemptRepository(conn)
    assert repo.recent_for_user("nobody") == []
