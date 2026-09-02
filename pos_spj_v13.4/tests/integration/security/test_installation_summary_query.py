from datetime import datetime, timezone

from backend.security.credentials.password_hasher import BcryptPasswordHasher
from backend.security.credentials.password_policy import PasswordPolicy
from backend.security.provisioning.installation_repository import SqliteInstallationRepository
from backend.security.provisioning.installation_summary_query import InstallationSummaryQueryService
from backend.security.provisioning.provision_installation_use_case import ProvisionInstallationUseCase
from backend.security.provisioning.recovery_code_repository import SqliteRecoveryCodeRepository
from tests.integration._born_clean_db import make_db

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_summary_is_empty_before_provisioning():
    conn = make_db()
    summary = InstallationSummaryQueryService(conn).get_summary()
    assert summary.company_name == ""
    assert summary.branch_name == ""


def test_summary_reflects_provisioned_company_and_branch():
    conn = make_db()
    uc = ProvisionInstallationUseCase(
        conn, installation_repository=SqliteInstallationRepository(conn),
        recovery_code_repository=SqliteRecoveryCodeRepository(conn),
        password_hasher=BcryptPasswordHasher(), password_policy=PasswordPolicy(),
    )
    uc.execute(
        company_name="Carnicería SPJ", branch_name="Sucursal Centro", owner_username="jarralfa",
        owner_password="Correct-Horse-9!", owner_full_name="Jose Alfaro", now=T0,
    )
    conn.commit()

    summary = InstallationSummaryQueryService(conn).get_summary()
    assert summary.company_name == "Carnicería SPJ"
    assert summary.branch_name == "Sucursal Centro"
