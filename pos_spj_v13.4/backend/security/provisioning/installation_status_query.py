"""InstallationStatusQuery — SHELL-2 security foundation.

Read-only query used at every cold boot (and by the future
AuthenticationCoordinator) to decide whether to show `InitialSetupWizard`,
the normal login, a recovery screen, or a locked screen. A database that has
run migration 206 but never been provisioned has no `installation` row yet
— that reads as UNINITIALIZED, not an error.
"""
from __future__ import annotations

from backend.security.provisioning.installation import ProvisioningStatus
from backend.security.provisioning.installation_repository import InstallationRepository


class InstallationStatusQuery:
    def __init__(self, installation_repository: InstallationRepository) -> None:
        self._repo = installation_repository

    def current_status(self) -> ProvisioningStatus:
        installation = self._repo.get()
        if installation is None:
            return ProvisioningStatus.UNINITIALIZED
        return installation.provisioning_status

    def requires_setup_wizard(self) -> bool:
        return self.current_status() in (
            ProvisioningStatus.UNINITIALIZED, ProvisioningStatus.PROVISIONING,
        )

    def login_is_available(self) -> bool:
        return self.current_status() is ProvisioningStatus.PROVISIONED
