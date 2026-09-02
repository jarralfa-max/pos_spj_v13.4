from datetime import datetime, timedelta, timezone

from backend.security.recovery.recovery_token import RecoveryToken
from backend.security.recovery.recovery_token_repository import SqliteRecoveryTokenRepository
from tests.integration._born_clean_db import make_db

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_save_and_find_by_hash_roundtrip():
    conn = make_db()
    repo = SqliteRecoveryTokenRepository(conn)
    token = RecoveryToken.issue("juan", raw_token="raw-token-value", issued_at=T0)
    repo.save(token)
    conn.commit()

    found = repo.find_by_hash(token.token_hash)
    assert found is not None
    assert found.token_id == token.token_id
    assert found.user_reference == "juan"
    assert found.issued_at == T0
    assert found.used_at is None


def test_find_by_hash_returns_none_for_unknown_hash():
    conn = make_db()
    repo = SqliteRecoveryTokenRepository(conn)
    assert repo.find_by_hash("does-not-exist") is None


def test_find_active_for_user_excludes_used_tokens():
    conn = make_db()
    repo = SqliteRecoveryTokenRepository(conn)
    active = RecoveryToken.issue("juan", raw_token="a", issued_at=T0)
    used = RecoveryToken.issue("juan", raw_token="b", issued_at=T0).mark_used(used_at=T0)
    repo.save(active)
    repo.save(used)
    conn.commit()

    results = repo.find_active_for_user("juan")
    assert [t.token_id for t in results] == [active.token_id]


def test_replace_persists_used_at():
    conn = make_db()
    repo = SqliteRecoveryTokenRepository(conn)
    token = RecoveryToken.issue("juan", raw_token="a", issued_at=T0)
    repo.save(token)
    conn.commit()

    used = token.mark_used(used_at=T0 + timedelta(minutes=1))
    repo.replace(used)
    conn.commit()

    found = repo.find_by_hash(token.token_hash)
    assert found.used_at == T0 + timedelta(minutes=1)


def test_find_active_for_user_scoped_per_user():
    conn = make_db()
    repo = SqliteRecoveryTokenRepository(conn)
    repo.save(RecoveryToken.issue("juan", raw_token="a", issued_at=T0))
    repo.save(RecoveryToken.issue("maria", raw_token="b", issued_at=T0))
    conn.commit()

    assert len(repo.find_active_for_user("juan")) == 1
    assert len(repo.find_active_for_user("maria")) == 1
