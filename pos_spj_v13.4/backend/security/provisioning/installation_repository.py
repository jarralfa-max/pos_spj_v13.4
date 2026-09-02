"""InstallationRepository — SHELL-2 security foundation.

Unlike SHELL-1's Recovery/Session repositories (deliberately left as
in-memory-only until they're wired into a live auth flow), `Installation`
must survive process restarts from day one — "does this install still need
the setup wizard?" is answered on every cold boot, before login exists at
all. `SqliteInstallationRepository` is therefore the real, production
adapter; `InMemoryInstallationRepository` exists only for pure unit tests
that don't want a database.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from backend.security.provisioning.installation import Installation, ProvisioningStatus
from backend.shared.ids import INSTALLATION_SINGLETON_UUID


@runtime_checkable
class InstallationRepository(Protocol):
    def get(self) -> Installation | None:
        """The singleton installation row, or None if migration 206 hasn't
        run / no row was ever created yet."""
        ...

    def save(self, installation: Installation) -> None:
        """Upsert the singleton row."""
        ...


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _format_dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class SqliteInstallationRepository:
    def __init__(self, conn) -> None:
        self._conn = conn

    def get(self) -> Installation | None:
        row = self._conn.execute(
            "SELECT id, installation_code, company_id, initial_branch_id, "
            "workstation_id, provisioning_status, provisioned_at, "
            "provisioned_by_user_id, schema_version, application_version, "
            "created_at, updated_at FROM installation WHERE id = ?",
            (INSTALLATION_SINGLETON_UUID,),
        ).fetchone()
        if row is None:
            return None
        return Installation(
            id=row["id"],
            installation_code=row["installation_code"],
            company_id=row["company_id"],
            initial_branch_id=row["initial_branch_id"],
            workstation_id=row["workstation_id"],
            provisioning_status=ProvisioningStatus(row["provisioning_status"]),
            provisioned_at=_parse_dt(row["provisioned_at"]),
            provisioned_by_user_id=row["provisioned_by_user_id"],
            schema_version=row["schema_version"],
            application_version=row["application_version"],
            created_at=_parse_dt(row["created_at"]),
            updated_at=_parse_dt(row["updated_at"]),
        )

    def save(self, installation: Installation) -> None:
        self._conn.execute(
            """
            INSERT INTO installation (
                id, installation_code, company_id, initial_branch_id,
                workstation_id, provisioning_status, provisioned_at,
                provisioned_by_user_id, schema_version, application_version,
                created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                installation_code = excluded.installation_code,
                company_id = excluded.company_id,
                initial_branch_id = excluded.initial_branch_id,
                workstation_id = excluded.workstation_id,
                provisioning_status = excluded.provisioning_status,
                provisioned_at = excluded.provisioned_at,
                provisioned_by_user_id = excluded.provisioned_by_user_id,
                schema_version = excluded.schema_version,
                application_version = excluded.application_version,
                updated_at = excluded.updated_at
            """,
            (
                installation.id, installation.installation_code, installation.company_id,
                installation.initial_branch_id, installation.workstation_id,
                installation.provisioning_status.value,
                _format_dt(installation.provisioned_at), installation.provisioned_by_user_id,
                installation.schema_version, installation.application_version,
                _format_dt(installation.created_at), _format_dt(installation.updated_at),
            ),
        )


class InMemoryInstallationRepository:
    def __init__(self) -> None:
        self._installation: Installation | None = None

    def get(self) -> Installation | None:
        return self._installation

    def save(self, installation: Installation) -> None:
        self._installation = installation
