"""Provisioned company/workstation IDs must resolve to their owning records."""
import pytest

from backend.domain.settings.enums import WorkstationStatus, WorkstationType
from backend.infrastructure.db.repositories.settings.company_profile_repository import (
    SqliteCompanyProfileRepository,
)
from backend.infrastructure.db.repositories.settings.workstation_repository import (
    SqliteWorkstationRepository,
)
from backend.security.provisioning.installation_summary_query import InstallationSummaryQueryService
from backend.shared.ids import validate_uuidv7
from tests.integration._born_clean_db import make_db
from tests.integration.security.test_provision_installation_use_case import _build_use_case, _execute


@pytest.fixture
def connection():
    conn = make_db()
    yield conn
    conn.close()


def test_provisioning_persists_the_referenced_company_and_workstation(connection):
    result = _execute(_build_use_case(connection))
    installation = result.installation
    company = SqliteCompanyProfileRepository(connection).get(installation.company_id)
    workstation = SqliteWorkstationRepository(connection).get(installation.workstation_id)

    assert company is not None
    assert company.legal_name == "Carnicería SPJ"
    assert company.tax_id == "SPJ010101AAA"
    assert workstation is not None
    assert workstation.name == "Caja 1"
    assert workstation.branch_id == installation.initial_branch_id
    assert workstation.workstation_type is WorkstationType.POS
    assert workstation.status is WorkstationStatus.ACTIVE
    for entity_id in (company.id, workstation.id, workstation.branch_id):
        assert validate_uuidv7(entity_id) == entity_id
    assert len({company.id, workstation.id, workstation.branch_id, result.owner_user_id}) == 4
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert not connection.in_transaction


def test_provisioning_does_not_duplicate_profile_identity_in_configuration(connection):
    _execute(_build_use_case(connection))
    rows = connection.execute(
        "SELECT clave FROM configuraciones WHERE clave IN "
        "('company_id', 'empresa_nombre', 'empresa_rfc', 'workstation_nombre')"
    ).fetchall()
    assert rows == []


@pytest.mark.parametrize("autocommit", [False, True])
def test_failed_provisioning_rolls_back_profiles_and_retry_creates_one_each(connection, autocommit):
    if autocommit:
        connection.isolation_level = None

    def fail_after_profiles_exist(event, _payload):
        if event == "INSTALLATION_PROVISIONED":
            assert connection.execute("SELECT COUNT(*) FROM company_profiles").fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM workstations").fetchone()[0] == 1
            raise RuntimeError("completion audit unavailable")

    with pytest.raises(RuntimeError, match="completion audit unavailable"):
        _execute(_build_use_case(connection, audit_sink=fail_after_profiles_exist))
    assert not connection.in_transaction
    for table in ("company_profiles", "workstations", "usuarios", "installation_recovery_codes"):
        assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0

    result = _execute(_build_use_case(connection))
    for table in ("company_profiles", "workstations", "usuarios"):
        assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 1
    assert SqliteCompanyProfileRepository(connection).get(result.installation.company_id) is not None


def test_login_summary_reads_the_current_company_profile(connection):
    result = _execute(_build_use_case(connection))
    repository = SqliteCompanyProfileRepository(connection)
    company = repository.get(result.installation.company_id)
    assert company is not None
    company.update_identity(
        legal_name="Comercializadora Centro", default_currency=company.default_currency,
        default_timezone=company.default_timezone, default_locale=company.default_locale,
    )
    repository.save(company)
    connection.commit()

    summary = InstallationSummaryQueryService(connection).get_summary()
    assert summary.company_name == "Comercializadora Centro"
    assert summary.branch_name == "Sucursal Centro"
