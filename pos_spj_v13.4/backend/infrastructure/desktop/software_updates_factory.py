"""Desktop composition of the software-update use cases — ONE composition for
the three hosts: the startup sequence (`frontend/desktop/app.py`), the
Configuración page «Acerca de y actualizaciones» and the background trigger
of the maintenance window.

The station key is the MACHINE (`default_workstation_id()`, the host name):
software is installed per machine, whoever logs in.
"""
from __future__ import annotations

import shutil

from backend.application.configuracion.authorization import (
    ConfiguracionAuthorizationPolicy,
    SessionPermissionChecker,
)
from backend.application.software_updates.installation import SoftwareInstallation
from backend.application.software_updates.use_cases import (
    SoftwareUpdateDependencies,
    StationContext,
)
from backend.bootstrap.application_context import default_workstation_id
from backend.infrastructure.db.repositories.settings.configuracion_security_repositories import (
    ConfiguracionAuditLogRepository,
)
from backend.infrastructure.db.repositories.software_updates.station_update_repository import (
    SqliteActiveOperationsProbe,
    SqliteStationUpdateRepository,
)
from backend.infrastructure.db.sqlite_backup import database_schema_version
from backend.infrastructure.updater.trusted_keys import embedded_keyring
from backend.infrastructure.updater.update_downloader import (
    UpdateDownloader,
    verify_package_file,
)
from backend.infrastructure.updater.update_job_store import UpdateJobStore
from backend.infrastructure.updater.update_manifest import SignedManifestReader
from backend.shared.app_paths import AppPaths


class _NoUserAuthorization:
    """Startup and background ticks act as the system, never as a user:
    any use case that requires a permission is refused."""

    def require(self, user_id: str, permission_code: str) -> None:
        raise PermissionError("Operación del sistema sin usuario.")

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return False


def build_software_update_dependencies(
    connection, *, session_context=None, paths: AppPaths | None = None,
    installation: SoftwareInstallation | None = None,
) -> SoftwareUpdateDependencies:
    paths = paths or AppPaths.from_environment()
    installation = installation or SoftwareInstallation.describe(paths)
    if session_context is not None:
        authorization = ConfiguracionAuthorizationPolicy(SessionPermissionChecker(session_context))
        user_id = str(getattr(session_context, "user_id", "") or "")
        branch_id = str(getattr(session_context, "sucursal_id", "") or "")
    else:
        authorization = _NoUserAuthorization()
        user_id = ""
        branch_id = ""
    keyring = embedded_keyring()
    return SoftwareUpdateDependencies(
        connection=connection,
        installation=installation,
        station=StationContext(workstation_key=default_workstation_id(), branch_id=branch_id,
                               user_id=user_id),
        authorization=authorization,
        repository=SqliteStationUpdateRepository(connection),
        reader=SignedManifestReader(keyring),
        downloader=UpdateDownloader(paths.downloads_dir,
                                    allowed_hosts=installation.allowed_hosts),
        job_store=UpdateJobStore(paths.update_job_path),
        probe=SqliteActiveOperationsProbe(connection),
        audit=ConfiguracionAuditLogRepository(connection),
        verify_package=verify_package_file,
        schema_version=lambda: database_schema_version(connection),
        signing_configured=not keyring.is_empty,
    )


def copy_package_file(source, destination) -> None:
    """Offline media → downloads folder (a plain file copy: the installer is
    not a database; its hash is verified again after the copy)."""
    shutil.copyfile(source, destination)
