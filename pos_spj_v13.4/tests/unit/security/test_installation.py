from datetime import datetime, timezone

import pytest

from backend.security.provisioning.installation import Installation, ProvisioningStatus
from backend.shared.ids import INSTALLATION_SINGLETON_UUID

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_uninitialized_has_expected_defaults():
    installation = Installation.uninitialized(installation_code="INST-001", now=T0)
    assert installation.id == INSTALLATION_SINGLETON_UUID
    assert installation.provisioning_status is ProvisioningStatus.UNINITIALIZED
    assert installation.company_id is None
    assert installation.is_provisioned() is False
    assert installation.requires_setup_wizard() is True


def test_start_provisioning_transitions_state():
    installation = Installation.uninitialized(installation_code="INST-001", now=T0)
    started = installation.start_provisioning(now=T0)
    assert started.provisioning_status is ProvisioningStatus.PROVISIONING
    assert started.requires_setup_wizard() is True
    assert started.is_provisioned() is False


def test_start_provisioning_from_wrong_state_raises():
    installation = Installation.uninitialized(installation_code="INST-001", now=T0).start_provisioning(now=T0)
    with pytest.raises(ValueError):
        installation.start_provisioning(now=T0)


def test_complete_provisioning_transitions_to_provisioned():
    installation = Installation.uninitialized(installation_code="INST-001", now=T0).start_provisioning(now=T0)
    completed = installation.complete_provisioning(
        company_id="company-1", initial_branch_id="branch-1", workstation_id="ws-1",
        provisioned_by_user_id="owner-1", now=T0,
    )
    assert completed.provisioning_status is ProvisioningStatus.PROVISIONED
    assert completed.is_provisioned() is True
    assert completed.requires_setup_wizard() is False
    assert completed.company_id == "company-1"
    assert completed.provisioned_at == T0


def test_complete_provisioning_without_starting_raises():
    installation = Installation.uninitialized(installation_code="INST-001", now=T0)
    with pytest.raises(ValueError):
        installation.complete_provisioning(
            company_id="c", initial_branch_id="b", workstation_id="w",
            provisioned_by_user_id="o", now=T0,
        )


def test_lock_and_require_recovery_transitions():
    installation = Installation.uninitialized(installation_code="INST-001", now=T0)
    locked = installation.lock(now=T0)
    assert locked.provisioning_status is ProvisioningStatus.LOCKED

    needs_recovery = installation.require_recovery(now=T0)
    assert needs_recovery.provisioning_status is ProvisioningStatus.RECOVERY_REQUIRED


def test_installation_is_frozen_and_transitions_return_new_instances():
    installation = Installation.uninitialized(installation_code="INST-001", now=T0)
    started = installation.start_provisioning(now=T0)
    assert installation.provisioning_status is ProvisioningStatus.UNINITIALIZED
    assert started is not installation
