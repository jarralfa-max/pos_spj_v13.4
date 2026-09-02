"""Installation — SHELL-2 security foundation.

The provisioning lifecycle state for this deployed instance. Exactly one
`Installation` exists per database (singleton row at
`backend.shared.ids.INSTALLATION_SINGLETON_UUID`) — see
`installation_schema.py` for the table and `InstallationRepository` for how
it's loaded/persisted.

Normal login is only reachable when `provisioning_status == PROVISIONED`
(see `InstallationNotProvisionedError`); everything else routes to
`InitialSetupWizard` or a recovery/locked screen instead.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from backend.shared.ids import INSTALLATION_SINGLETON_UUID


class ProvisioningStatus(str, Enum):
    UNINITIALIZED = "UNINITIALIZED"
    PROVISIONING = "PROVISIONING"
    PROVISIONED = "PROVISIONED"
    LOCKED = "LOCKED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


@dataclass(frozen=True)
class Installation:
    id: str
    installation_code: str
    company_id: str | None
    initial_branch_id: str | None
    workstation_id: str | None
    provisioning_status: ProvisioningStatus
    provisioned_at: datetime | None
    provisioned_by_user_id: str | None
    schema_version: str | None
    application_version: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def uninitialized(
        cls, *, installation_code: str, now: datetime, schema_version: str | None = None,
        application_version: str | None = None,
    ) -> "Installation":
        """The state a brand-new database starts in before provisioning."""
        return cls(
            id=INSTALLATION_SINGLETON_UUID,
            installation_code=installation_code,
            company_id=None,
            initial_branch_id=None,
            workstation_id=None,
            provisioning_status=ProvisioningStatus.UNINITIALIZED,
            provisioned_at=None,
            provisioned_by_user_id=None,
            schema_version=schema_version,
            application_version=application_version,
            created_at=now,
            updated_at=now,
        )

    def is_provisioned(self) -> bool:
        return self.provisioning_status is ProvisioningStatus.PROVISIONED

    def requires_setup_wizard(self) -> bool:
        return self.provisioning_status in (
            ProvisioningStatus.UNINITIALIZED, ProvisioningStatus.PROVISIONING,
        )

    def start_provisioning(self, *, now: datetime) -> "Installation":
        if self.provisioning_status is not ProvisioningStatus.UNINITIALIZED:
            raise ValueError(
                f"No se puede iniciar el aprovisionamiento desde el estado "
                f"{self.provisioning_status.value}."
            )
        return self._replace(provisioning_status=ProvisioningStatus.PROVISIONING, updated_at=now)

    def complete_provisioning(
        self, *, company_id: str, initial_branch_id: str, workstation_id: str,
        provisioned_by_user_id: str, now: datetime,
    ) -> "Installation":
        if self.provisioning_status is not ProvisioningStatus.PROVISIONING:
            raise ValueError(
                f"No se puede completar el aprovisionamiento desde el estado "
                f"{self.provisioning_status.value}."
            )
        return self._replace(
            provisioning_status=ProvisioningStatus.PROVISIONED,
            company_id=company_id,
            initial_branch_id=initial_branch_id,
            workstation_id=workstation_id,
            provisioned_by_user_id=provisioned_by_user_id,
            provisioned_at=now,
            updated_at=now,
        )

    def lock(self, *, now: datetime) -> "Installation":
        return self._replace(provisioning_status=ProvisioningStatus.LOCKED, updated_at=now)

    def require_recovery(self, *, now: datetime) -> "Installation":
        return self._replace(provisioning_status=ProvisioningStatus.RECOVERY_REQUIRED, updated_at=now)

    def _replace(self, **overrides) -> "Installation":
        fields = {
            "id": self.id, "installation_code": self.installation_code,
            "company_id": self.company_id, "initial_branch_id": self.initial_branch_id,
            "workstation_id": self.workstation_id,
            "provisioning_status": self.provisioning_status,
            "provisioned_at": self.provisioned_at,
            "provisioned_by_user_id": self.provisioned_by_user_id,
            "schema_version": self.schema_version,
            "application_version": self.application_version,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }
        fields.update(overrides)
        return Installation(**fields)
