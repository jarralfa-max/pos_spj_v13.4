"""ProvisionInstallationUseCase — SHELL-2 security foundation.

Top-level orchestrator behind `InitialSetupWizard`'s "finish" step: creates
the initial branch (reusing the existing `sucursales` schema), the canonical
`CompanyProfile` and `Workstation` records the installation then points at,
the first owner account (`CreateInitialOwnerUseCase`), the installation's
recovery kit, and transitions `Installation` from UNINITIALIZED to
PROVISIONED.

`company_id`/`workstation_id` used to be minted here as bare UUIDs whose
identity lived in `configuraciones` key/value rows, so they referenced no
record at all while the Settings bounded context owned real
`company_profiles`/`workstations` tables that provisioning never wrote — two
parallel homes for the same identity. Both are now created through their
canonical repositories inside this same UnitOfWork, and the KV copies are
gone; `sucursal_instalacion_id` stays because `core/services/branch_resolution.py`
is a real consumer of it.

Owns an exclusive UnitOfWork: success is returned only after commit. A failed
attempt rolls back identity, installation state, configuration and recovery
codes together; a retry starts from the last committed state.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from backend.domain.settings.entities.company_profile import CompanyProfile
from backend.domain.settings.entities.workstation import Workstation
from backend.domain.settings.enums import WorkstationType
from backend.infrastructure.db.repositories.security.provisioning_unit_of_work import ProvisioningUnitOfWork
from backend.infrastructure.db.repositories.settings.company_profile_repository import (
    SqliteCompanyProfileRepository,
)
from backend.infrastructure.db.repositories.settings.workstation_repository import (
    SqliteWorkstationRepository,
)

from backend.security.audit.security_events import (
    INSTALLATION_PROVISIONED,
    INSTALLATION_PROVISIONING_STARTED,
)
from backend.security.credentials.password_hasher import PasswordHasher
from backend.security.credentials.password_policy import PasswordPolicy
from backend.security.provisioning.create_initial_owner_use_case import CreateInitialOwnerUseCase
from backend.security.provisioning.errors import (
    InstallationAlreadyProvisionedError,
    InstallationLockedError,
)
from backend.security.provisioning.installation import Installation, ProvisioningStatus
from backend.security.provisioning.installation_recovery_kit import InstallationRecoveryKit
from backend.security.provisioning.installation_repository import InstallationRepository
from backend.security.provisioning.recovery_code_repository import RecoveryCodeRepository
from backend.shared.ids import new_uuid

AuditSink = Callable[[str, dict], None]

# The setup wizard does not collect locale/currency yet; these stay overridable
# per call so it can start doing so without another provisioning path.
DEFAULT_CURRENCY = "MXN"
DEFAULT_TIMEZONE = "America/Mexico_City"
DEFAULT_LOCALE = "es-MX"


def _workstation_code(workstation_name: str) -> str:
    """`workstations.code` is NOT NULL UNIQUE and the wizard only asks for a
    display name, so derive a slug from it. A name made entirely of
    punctuation would slug to the empty string, which the CHECK constraint
    rejects — fall back to a minted, guaranteed-non-empty code."""
    slug = "".join(ch if ch.isalnum() else "-" for ch in workstation_name.strip().upper())
    slug = "-".join(part for part in slug.split("-") if part)
    return slug or f"POS-{new_uuid()[:8].upper()}"


@dataclass(frozen=True)
class ProvisioningResult:
    installation: Installation
    owner_user_id: str
    recovery_codes: list[str]


class ProvisionInstallationUseCase:
    def __init__(
        self,
        conn,
        *,
        installation_repository: InstallationRepository,
        recovery_code_repository: RecoveryCodeRepository,
        password_hasher: PasswordHasher,
        password_policy: PasswordPolicy,
        audit_sink: Optional[AuditSink] = None,
    ) -> None:
        self._conn = conn
        self._installations = installation_repository
        self._recovery_kit = InstallationRecoveryKit(code_repository=recovery_code_repository)
        self._hasher = password_hasher
        self._policy = password_policy
        self._audit = audit_sink or (lambda event, payload: None)

    def execute(
        self,
        *,
        company_name: str,
        company_rfc: str = "",
        branch_name: str,
        branch_address: str = "",
        workstation_name: str = "",
        owner_username: str,
        owner_password: str,
        owner_full_name: str,
        owner_recovery_contact: str = "",
        recovery_code_count: int = 10,
        default_currency: str = DEFAULT_CURRENCY,
        default_timezone: str = DEFAULT_TIMEZONE,
        default_locale: str = DEFAULT_LOCALE,
        now: datetime | None = None,
    ) -> ProvisioningResult:
        for field, value in (("company_name", company_name), ("branch_name", branch_name),
                             ("workstation_name", workstation_name)):
            if not value or not value.strip():
                raise ValueError(f"{field} es obligatorio.")
        with ProvisioningUnitOfWork(self._conn):
            return self._provision(
                company_name=company_name, company_rfc=company_rfc,
                branch_name=branch_name, branch_address=branch_address,
                workstation_name=workstation_name, owner_username=owner_username,
                owner_password=owner_password, owner_full_name=owner_full_name,
                owner_recovery_contact=owner_recovery_contact,
                recovery_code_count=recovery_code_count,
                default_currency=default_currency, default_timezone=default_timezone,
                default_locale=default_locale, now=now,
            )

    def _provision(
        self, *, company_name, company_rfc, branch_name, branch_address,
        workstation_name, owner_username, owner_password, owner_full_name,
        owner_recovery_contact, recovery_code_count, default_currency,
        default_timezone, default_locale, now,
    ) -> ProvisioningResult:
        now = now or datetime.now(timezone.utc)
        installation = self._installations.get() or Installation.uninitialized(
            installation_code=new_uuid(), now=now,
        )

        if installation.provisioning_status is ProvisioningStatus.PROVISIONED:
            raise InstallationAlreadyProvisionedError(
                "Esta instalación ya fue aprovisionada; el asistente no puede ejecutarse de nuevo."
            )
        if installation.provisioning_status in (
            ProvisioningStatus.LOCKED, ProvisioningStatus.RECOVERY_REQUIRED,
        ):
            raise InstallationLockedError(
                f"No se puede aprovisionar: la instalación está en estado "
                f"{installation.provisioning_status.value}."
            )

        if installation.provisioning_status is ProvisioningStatus.UNINITIALIZED:
            installation = installation.start_provisioning(now=now)
            self._installations.save(installation)
            self._audit(INSTALLATION_PROVISIONING_STARTED, {"installation_id": installation.id})

        branch_id = new_uuid()
        self._conn.execute(
            "INSERT INTO sucursales (id, nombre, direccion, activa) VALUES (?,?,?,1)",
            (branch_id, branch_name.strip(), (branch_address or "").strip()),
        )

        company = CompanyProfile.create(
            legal_name=company_name, tax_id=(company_rfc or ""),
            default_currency=default_currency, default_timezone=default_timezone,
            default_locale=default_locale,
        )
        SqliteCompanyProfileRepository(self._conn).save(company)

        workstation = Workstation.create(
            branch_id=branch_id, code=_workstation_code(workstation_name),
            name=workstation_name, workstation_type=WorkstationType.POS,
        )
        SqliteWorkstationRepository(self._conn).save(workstation)

        self._conn.execute(
            "INSERT INTO configuraciones (clave, valor) VALUES (?, ?) "
            "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
            ("sucursal_instalacion_id", branch_id),
        )

        owner_use_case = CreateInitialOwnerUseCase(
            self._conn, password_hasher=self._hasher, password_policy=self._policy,
        )
        owner_user_id = owner_use_case.execute(
            username=owner_username,
            password=owner_password,
            full_name=owner_full_name,
            branch_id=branch_id,
            recovery_contact=owner_recovery_contact,
        )

        recovery_codes = self._recovery_kit.generate(
            installation.id, count=recovery_code_count, now=now,
        )

        installation = installation.complete_provisioning(
            company_id=company.id, initial_branch_id=branch_id, workstation_id=workstation.id,
            provisioned_by_user_id=owner_user_id, now=now,
        )
        self._installations.save(installation)
        self._audit(INSTALLATION_PROVISIONED, {"installation_id": installation.id})

        return ProvisioningResult(
            installation=installation, owner_user_id=owner_user_id, recovery_codes=recovery_codes,
        )
