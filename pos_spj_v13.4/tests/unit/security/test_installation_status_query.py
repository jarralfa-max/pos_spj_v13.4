from datetime import datetime, timezone

from backend.security.provisioning.installation import Installation, ProvisioningStatus
from backend.security.provisioning.installation_repository import InMemoryInstallationRepository
from backend.security.provisioning.installation_status_query import InstallationStatusQuery

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_no_row_reads_as_uninitialized():
    query = InstallationStatusQuery(InMemoryInstallationRepository())
    assert query.current_status() is ProvisioningStatus.UNINITIALIZED
    assert query.requires_setup_wizard() is True
    assert query.login_is_available() is False


def test_provisioned_installation_allows_login():
    repo = InMemoryInstallationRepository()
    installation = (
        Installation.uninitialized(installation_code="INST-001", now=T0)
        .start_provisioning(now=T0)
        .complete_provisioning(
            company_id="c", initial_branch_id="b", workstation_id="w",
            provisioned_by_user_id="o", now=T0,
        )
    )
    repo.save(installation)

    query = InstallationStatusQuery(repo)
    assert query.current_status() is ProvisioningStatus.PROVISIONED
    assert query.requires_setup_wizard() is False
    assert query.login_is_available() is True


def test_provisioning_in_progress_still_requires_wizard():
    repo = InMemoryInstallationRepository()
    repo.save(Installation.uninitialized(installation_code="INST-001", now=T0).start_provisioning(now=T0))

    query = InstallationStatusQuery(repo)
    assert query.requires_setup_wizard() is True
    assert query.login_is_available() is False


def test_locked_installation_blocks_both_wizard_and_login():
    repo = InMemoryInstallationRepository()
    repo.save(Installation.uninitialized(installation_code="INST-001", now=T0).lock(now=T0))

    query = InstallationStatusQuery(repo)
    assert query.requires_setup_wizard() is False
    assert query.login_is_available() is False
