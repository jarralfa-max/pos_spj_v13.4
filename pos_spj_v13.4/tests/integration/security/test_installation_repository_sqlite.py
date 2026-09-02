from datetime import datetime, timezone

from backend.security.provisioning.installation import Installation, ProvisioningStatus
from backend.security.provisioning.installation_repository import SqliteInstallationRepository
from backend.shared.ids import INSTALLATION_SINGLETON_UUID
from tests.integration._born_clean_db import make_db

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_get_returns_none_on_fresh_db():
    conn = make_db()
    repo = SqliteInstallationRepository(conn)
    assert repo.get() is None


def test_save_then_get_roundtrips():
    conn = make_db()
    repo = SqliteInstallationRepository(conn)
    installation = Installation.uninitialized(installation_code="INST-001", now=T0)
    repo.save(installation)
    conn.commit()

    fetched = repo.get()
    assert fetched is not None
    assert fetched.id == INSTALLATION_SINGLETON_UUID
    assert fetched.installation_code == "INST-001"
    assert fetched.provisioning_status is ProvisioningStatus.UNINITIALIZED
    assert fetched.created_at == T0


def test_save_upserts_the_singleton_row():
    conn = make_db()
    repo = SqliteInstallationRepository(conn)
    installation = Installation.uninitialized(installation_code="INST-001", now=T0)
    repo.save(installation)
    repo.save(installation.start_provisioning(now=T0))
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM installation").fetchone()[0]
    assert count == 1
    assert repo.get().provisioning_status is ProvisioningStatus.PROVISIONING


def test_full_lifecycle_persists_correctly():
    conn = make_db()
    repo = SqliteInstallationRepository(conn)
    installation = (
        Installation.uninitialized(installation_code="INST-001", now=T0)
        .start_provisioning(now=T0)
        .complete_provisioning(
            company_id="company-1", initial_branch_id="branch-1", workstation_id="ws-1",
            provisioned_by_user_id="owner-1", now=T0,
        )
    )
    repo.save(installation)
    conn.commit()

    fetched = repo.get()
    assert fetched.provisioning_status is ProvisioningStatus.PROVISIONED
    assert fetched.company_id == "company-1"
    assert fetched.initial_branch_id == "branch-1"
    assert fetched.workstation_id == "ws-1"
    assert fetched.provisioned_by_user_id == "owner-1"
    assert fetched.provisioned_at == T0
