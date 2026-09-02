"""Canonical installation/provisioning errors — SHELL-2 security foundation."""
from __future__ import annotations


class InstallationNotProvisionedError(RuntimeError):
    """An operation that requires `provisioning_status == PROVISIONED` was
    attempted (e.g. normal login) while the installation is still
    UNINITIALIZED, PROVISIONING, or RECOVERY_REQUIRED."""


class InstallationAlreadyProvisionedError(RuntimeError):
    """`ProvisionInstallationUseCase` was invoked a second time. Provisioning
    is a one-time, idempotency-guarded operation — there is no "re-run the
    wizard" path once PROVISIONED."""


class InstallationLockedError(RuntimeError):
    """The installation is LOCKED — no authentication or provisioning
    operation may proceed until an administrator/recovery flow unlocks it."""
