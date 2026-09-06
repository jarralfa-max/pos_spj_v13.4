from datetime import datetime, timezone

from backend.bootstrap.application_context_builder import ApplicationContextBuilder
from backend.security.authentication.authenticate_user_use_case import AuthenticateUserUseCase
from backend.security.authentication.authentication_attempt_repository import (
    SqliteAuthenticationAttemptRepository,
)
from backend.security.authentication.user_credentials import SqliteUserCredentialsRepository
from backend.security.credentials.password_hasher import Argon2idPasswordHasher, BcryptPasswordHasher
from backend.security.credentials.password_policy import PasswordPolicy
from backend.security.credentials.password_verification import MultiSchemePasswordVerifier
from backend.security.provisioning.installation_repository import SqliteInstallationRepository
from backend.security.provisioning.provision_installation_use_case import ProvisionInstallationUseCase
from backend.security.provisioning.recovery_code_repository import SqliteRecoveryCodeRepository
from backend.security.sessions.account_lockout_policy import AccountLockoutPolicy
from backend.security.sessions.session_manager import SessionManager
from backend.security.sessions.session_repository import InMemorySessionRepository
from tests.integration._born_clean_db import make_db

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _authenticated_conn_and_result():
    conn = make_db()
    provision_uc = ProvisionInstallationUseCase(
        conn, installation_repository=SqliteInstallationRepository(conn),
        recovery_code_repository=SqliteRecoveryCodeRepository(conn),
        password_hasher=BcryptPasswordHasher(), password_policy=PasswordPolicy(),
    )
    provision_uc.execute(
        company_name="Carnicería SPJ", branch_name="Sucursal Centro", owner_username="jarralfa",
        workstation_name="Estación de prueba",
        owner_password="Correct-Horse-9!", owner_full_name="Jose Alfaro", now=T0,
    )
    conn.commit()

    auth_uc = AuthenticateUserUseCase(
        credentials_repository=SqliteUserCredentialsRepository(conn),
        attempt_repository=SqliteAuthenticationAttemptRepository(conn),
        password_verifier=MultiSchemePasswordVerifier(
            primary=Argon2idPasswordHasher(), legacy=(BcryptPasswordHasher(),),
        ),
        lockout_policy=AccountLockoutPolicy(),
        session_manager=SessionManager(session_repository=InMemorySessionRepository()),
    )
    auth_result = auth_uc.execute(username="jarralfa", password="Correct-Horse-9!", workstation_id="ws-1", now=T0)
    conn.commit()
    return conn, auth_result


def test_builds_context_with_correct_identity_fields():
    conn, auth_result = _authenticated_conn_and_result()
    ctx = ApplicationContextBuilder(conn).build(auth_result)

    assert ctx.user_id == auth_result.credentials.id
    assert ctx.user_name == "Jose Alfaro"
    assert ctx.roles == ("system_owner",)
    assert ctx.session_id == auth_result.session.session_id
    assert ctx.workstation_id == "ws-1"


def test_builds_context_with_resolved_branch_and_company():
    conn, auth_result = _authenticated_conn_and_result()
    ctx = ApplicationContextBuilder(conn).build(auth_result)

    assert ctx.branch_id == auth_result.credentials.branch_id
    assert ctx.branch_name == "Sucursal Centro"
    assert ctx.company_id  # minted by ProvisionInstallationUseCase
    assert ctx.installation_id  # the singleton installation id


def test_builds_context_with_real_permissions_loaded():
    conn, auth_result = _authenticated_conn_and_result()
    ctx = ApplicationContextBuilder(conn).build(auth_result)

    # system_owner was seeded (migration 206) with full grants
    assert len(ctx.permissions) > 0
    assert ctx.is_admin() is True


def test_builds_context_with_feature_context():
    conn, auth_result = _authenticated_conn_and_result()
    ctx = ApplicationContextBuilder(conn).build(auth_result)
    assert ctx.feature_context is not None
