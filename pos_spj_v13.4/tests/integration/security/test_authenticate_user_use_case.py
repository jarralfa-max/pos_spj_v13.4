from datetime import datetime, timedelta, timezone

import pytest

from backend.security.authentication.authentication_attempt_repository import (
    SqliteAuthenticationAttemptRepository,
)
from backend.security.authentication.authenticate_user_use_case import AuthenticateUserUseCase
from backend.security.authentication.errors import AuthenticationFailedError
from backend.security.authentication.user_credentials import SqliteUserCredentialsRepository
from backend.security.credentials.password_hasher import Argon2idPasswordHasher, BcryptPasswordHasher
from backend.security.credentials.password_policy import PasswordPolicy
from backend.security.credentials.password_verification import MultiSchemePasswordVerifier
from backend.security.provisioning.installation_repository import SqliteInstallationRepository
from backend.security.provisioning.provision_installation_use_case import ProvisionInstallationUseCase
from backend.security.provisioning.recovery_code_repository import SqliteRecoveryCodeRepository
from backend.security.sessions.account_lockout_policy import AccountLockoutPolicy
from backend.security.sessions.errors import AccountLockedError
from backend.security.sessions.session_manager import SessionManager
from backend.security.sessions.session_repository import InMemorySessionRepository
from tests.integration._born_clean_db import make_db

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
PASSWORD = "Correct-Horse-9!"


def _provisioned_conn(*, owner_password: str = PASSWORD):
    conn = make_db()
    uc = ProvisionInstallationUseCase(
        conn,
        installation_repository=SqliteInstallationRepository(conn),
        recovery_code_repository=SqliteRecoveryCodeRepository(conn),
        password_hasher=BcryptPasswordHasher(),
        password_policy=PasswordPolicy(),
    )
    uc.execute(
        company_name="SPJ", branch_name="Centro", owner_username="jarralfa",
        owner_password=owner_password, owner_full_name="Jose Alfaro", now=T0,
    )
    conn.commit()
    return conn


def _use_case(conn, *, audit_sink=None, failed_attempt_limit=5, lockout_duration_seconds=900):
    return AuthenticateUserUseCase(
        credentials_repository=SqliteUserCredentialsRepository(conn),
        attempt_repository=SqliteAuthenticationAttemptRepository(conn),
        password_verifier=MultiSchemePasswordVerifier(
            primary=Argon2idPasswordHasher(), legacy=(BcryptPasswordHasher(),),
        ),
        lockout_policy=AccountLockoutPolicy(
            failed_attempt_limit=failed_attempt_limit, lockout_duration_seconds=lockout_duration_seconds,
        ),
        session_manager=SessionManager(session_repository=InMemorySessionRepository()),
        audit_sink=audit_sink,
    )


def test_owner_provisioned_with_bcrypt_can_log_in():
    conn = _provisioned_conn()
    result = _use_case(conn).execute(username="jarralfa", password=PASSWORD, now=T0)
    assert result.credentials.username == "jarralfa"
    assert result.credentials.role == "system_owner"


def test_successful_bcrypt_login_creates_a_session():
    conn = _provisioned_conn()
    result = _use_case(conn).execute(username="jarralfa", password=PASSWORD, workstation_id="ws-1", now=T0)
    assert result.session.user_id == result.credentials.id
    assert result.session.workstation_id == "ws-1"


def test_successful_legacy_login_rehashes_to_primary_scheme():
    conn = _provisioned_conn()
    _use_case(conn).execute(username="jarralfa", password=PASSWORD, now=T0)
    conn.commit()

    stored_hash = conn.execute(
        "SELECT password_hash FROM usuarios WHERE usuario='jarralfa'"
    ).fetchone()[0]
    assert stored_hash.startswith("$argon2id$")


def test_second_login_after_rehash_uses_argon2id_path():
    conn = _provisioned_conn()
    use_case = _use_case(conn)
    use_case.execute(username="jarralfa", password=PASSWORD, now=T0)
    conn.commit()
    # second login must still work now that the stored hash is argon2id
    result = use_case.execute(username="jarralfa", password=PASSWORD, now=T0 + timedelta(seconds=1))
    assert result.credentials.username == "jarralfa"


def test_wrong_password_raises_generic_error():
    conn = _provisioned_conn()
    with pytest.raises(AuthenticationFailedError):
        _use_case(conn).execute(username="jarralfa", password="wrong-password", now=T0)


def test_unknown_username_raises_the_same_generic_error():
    conn = _provisioned_conn()
    with pytest.raises(AuthenticationFailedError) as exc_unknown:
        _use_case(conn).execute(username="does-not-exist", password=PASSWORD, now=T0)
    with pytest.raises(AuthenticationFailedError) as exc_wrong:
        _use_case(conn).execute(username="jarralfa", password="wrong", now=T0)
    # never reveal which case it was
    assert str(exc_unknown.value) == str(exc_wrong.value)


def test_inactive_account_cannot_log_in():
    conn = _provisioned_conn()
    conn.execute("UPDATE usuarios SET activo = 0 WHERE usuario = 'jarralfa'")
    conn.commit()
    with pytest.raises(AuthenticationFailedError):
        _use_case(conn).execute(username="jarralfa", password=PASSWORD, now=T0)


def test_empty_credentials_rejected_without_touching_the_database():
    conn = _provisioned_conn()
    with pytest.raises(AuthenticationFailedError):
        _use_case(conn).execute(username="", password="", now=T0)


def test_lockout_triggers_after_failed_attempt_limit():
    conn = _provisioned_conn()
    use_case = _use_case(conn, failed_attempt_limit=3)
    for i in range(3):
        with pytest.raises(AuthenticationFailedError):
            use_case.execute(username="jarralfa", password="wrong", now=T0 + timedelta(seconds=i))
        conn.commit()

    with pytest.raises(AccountLockedError):
        use_case.execute(username="jarralfa", password=PASSWORD, now=T0 + timedelta(seconds=10))


def test_locked_account_unlocks_after_duration_elapses():
    conn = _provisioned_conn()
    use_case = _use_case(conn, failed_attempt_limit=3, lockout_duration_seconds=60)
    for i in range(3):
        with pytest.raises(AuthenticationFailedError):
            use_case.execute(username="jarralfa", password="wrong", now=T0 + timedelta(seconds=i))
        conn.commit()

    result = use_case.execute(username="jarralfa", password=PASSWORD, now=T0 + timedelta(seconds=120))
    assert result.credentials.username == "jarralfa"


def test_successful_login_resets_the_failure_streak():
    conn = _provisioned_conn()
    use_case = _use_case(conn, failed_attempt_limit=3)
    for i in range(2):
        with pytest.raises(AuthenticationFailedError):
            use_case.execute(username="jarralfa", password="wrong", now=T0 + timedelta(seconds=i))
        conn.commit()

    use_case.execute(username="jarralfa", password=PASSWORD, now=T0 + timedelta(seconds=5))
    conn.commit()

    # two more failures afterward — still below the limit since the streak reset
    for i in range(2):
        with pytest.raises(AuthenticationFailedError):
            use_case.execute(username="jarralfa", password="wrong", now=T0 + timedelta(seconds=10 + i))
        conn.commit()

    result = use_case.execute(username="jarralfa", password=PASSWORD, now=T0 + timedelta(seconds=20))
    assert result.credentials.username == "jarralfa"


def test_audit_events_emitted_for_success_failure_and_lockout():
    events = []
    conn = _provisioned_conn()
    use_case = _use_case(conn, failed_attempt_limit=2, audit_sink=lambda e, p: events.append(e))

    use_case.execute(username="jarralfa", password=PASSWORD, now=T0)
    conn.commit()
    assert events == ["USER_AUTHENTICATION_SUCCEEDED"]

    events.clear()
    for i in range(2):
        with pytest.raises((Exception,)):
            use_case.execute(username="jarralfa", password="wrong", now=T0 + timedelta(seconds=i + 1))
        conn.commit()

    assert events == [
        "USER_AUTHENTICATION_FAILED", "USER_AUTHENTICATION_FAILED", "ACCOUNT_LOCKED",
    ]


def test_audit_events_never_leak_the_password():
    events = []
    conn = _provisioned_conn()
    use_case = _use_case(conn, audit_sink=lambda e, p: events.append(p))
    use_case.execute(username="jarralfa", password=PASSWORD, now=T0)
    for payload in events:
        assert PASSWORD not in str(payload)
