"""Presenter of «Acerca de y actualizaciones» — UI-facing wrapper over the
software-update use cases. No SQL, no file system, no network here: every
call goes to `backend/application/software_updates/use_cases.py`, and every
failure becomes an `(ok, mensaje)` pair the page shows as is.
"""
from __future__ import annotations

import logging
from typing import Callable

from backend.application.software_updates.use_cases import (
    CancelScheduledUpdateUseCase,
    ChangeUpdateChannelUseCase,
    CheckForUpdatesUseCase,
    DownloadUpdateUseCase,
    GetSoftwareStatusQuery,
    ImportOfflineUpdateUseCase,
    InstallTiming,
    LaunchRequest,
    PreparedDownload,
    ScheduleUpdateInstallUseCase,
    SetMaintenanceWindowUseCase,
    SoftwareUpdateDependencies,
    SoftwareUpdateError,
    UpdateDeferredError,
)
from backend.domain.settings.exceptions import (
    ConfigurationAuthorizationConfigurationError,
    ConfigurationPermissionDeniedError,
)

logger = logging.getLogger("spj.ui.software_updates")

_EXPECTED = (SoftwareUpdateError, ConfigurationPermissionDeniedError,
             ConfigurationAuthorizationConfigurationError, PermissionError, ValueError)


class SoftwareUpdatesPresenter:
    def __init__(
        self, dependencies: SoftwareUpdateDependencies, *,
        copy_file: Callable[[object, object], None],
        request_handoff: Callable[[LaunchRequest], bool],
    ) -> None:
        self._deps = dependencies
        self._copy_file = copy_file
        self._handoff = request_handoff

    # ── reads ─────────────────────────────────────────────────────────────
    def status(self):
        return GetSoftwareStatusQuery(self._deps).execute()

    # ── commands ──────────────────────────────────────────────────────────
    def check(self) -> tuple[bool, str]:
        return self._run(lambda: CheckForUpdatesUseCase(self._deps).execute(),
                         lambda result: (result.decision is not None
                                         and not result.decision.rejected, result.message))

    def prepare_download(self) -> tuple[PreparedDownload | None, str]:
        try:
            return DownloadUpdateUseCase(self._deps).prepare(), ""
        except _EXPECTED as exc:
            return None, str(exc)

    def finish_download(self, prepared: PreparedDownload, error: BaseException | None) -> tuple[bool, str]:
        try:
            DownloadUpdateUseCase(self._deps).record(prepared, error=error)
        except Exception:
            logger.exception("No se pudo registrar la descarga")
        if error is not None:
            return False, f"La descarga no se completó: {error}"
        return True, (f"Versión {prepared.manifest.version} descargada y verificada "
                      "(tamaño y SHA-256).")

    def import_offline(self, manifest_path: str) -> tuple[bool, str]:
        return self._run(
            lambda: ImportOfflineUpdateUseCase(self._deps, self._copy_file).execute(manifest_path),
            lambda manifest: (True, f"Paquete offline de la versión {manifest.version} "
                                    "verificado e importado."))

    def install_now(self) -> tuple[bool, str]:
        try:
            request = ScheduleUpdateInstallUseCase(self._deps).execute(InstallTiming.NOW)
        except UpdateDeferredError as exc:
            return False, str(exc) + " Termine esas operaciones o programe la ventana de mantenimiento."
        except _EXPECTED as exc:
            return False, str(exc)
        if self._handoff(request):
            return True, "Cerrando SPJ para instalar…"
        try:
            CancelScheduledUpdateUseCase(self._deps).execute()
        except Exception:
            logger.exception("No se pudo cancelar la actualización no iniciada")
        return False, "No se pudo iniciar el actualizador; no se cambió nada."

    def schedule_for_window(self) -> tuple[bool, str]:
        return self._run(
            lambda: ScheduleUpdateInstallUseCase(self._deps).execute(
                InstallTiming.MAINTENANCE_WINDOW),
            lambda job: (True, f"La versión {job.to_version} se instalará en la ventana "
                               f"{job.scheduled_window}, cuando no haya ventas ni cortes en curso."))

    def cancel_scheduled(self) -> tuple[bool, str]:
        return self._run(lambda: CancelScheduledUpdateUseCase(self._deps).execute(),
                         lambda _: (True, "Actualización programada cancelada."))

    def change_channel(self, channel: str) -> tuple[bool, str]:
        return self._run(lambda: ChangeUpdateChannelUseCase(self._deps).execute(channel),
                         lambda new: (True, f"Canal cambiado a {new.label}."))

    def set_maintenance_window(self, window: str) -> tuple[bool, str]:
        return self._run(
            lambda: SetMaintenanceWindowUseCase(self._deps).execute(window),
            lambda value: (True, f"Ventana de mantenimiento: {value}" if value
                           else "Ventana de mantenimiento eliminada."))

    @staticmethod
    def _run(action, describe) -> tuple[bool, str]:
        try:
            return describe(action())
        except _EXPECTED as exc:
            return False, str(exc)
        except Exception as exc:
            logger.exception("Fallo inesperado en actualizaciones")
            return False, f"Error inesperado: {exc}"
