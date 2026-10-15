"""Hand an update job to the external updater and let the desktop exit.

The updater must not run from the installation folder: the installer replaces
that folder, and Windows cannot overwrite a running executable. So the
single-file `spj_updater.exe` is copied to a private temporary folder first and
the copy is started — with an argument list, detached, no shell.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile

from backend.application.software_updates.installation import SoftwareInstallation
from backend.infrastructure.updater.process_control import launch_detached


class UpdaterLaunchError(RuntimeError):
    pass


class ExternalUpdaterLauncher:
    def __init__(self, installation: SoftwareInstallation) -> None:
        self._installation = installation

    def command(self, *, job_path: Path, wait_pid: int, mode: str = "install") -> list[str]:
        installation = self._installation
        paths = installation.paths
        executable = list(installation.updater_command)
        if paths.is_installed:
            original = Path(executable[0])
            if not original.is_file():
                raise UpdaterLaunchError(f"No se encontró el actualizador ({original}).")
            private_dir = Path(tempfile.mkdtemp(prefix="spj-updater-"))
            copy = private_dir / original.name
            shutil.copy2(original, copy)
            executable = [str(copy)]
        command = [
            *executable, "--mode", mode, "--job", str(job_path), "--wait-pid", str(wait_pid),
            "--install-dir", str(paths.root), "--data-dir", str(paths.user_data_dir),
            "--installer-cache", str(paths.installer_cache_dir),
        ]
        if installation.build.signed:
            command.append("--require-signature")
        return command

    def launch(self, *, job_path: Path, wait_pid: int | None = None, mode: str = "install") -> int:
        command = self.command(job_path=job_path, wait_pid=wait_pid or os.getpid(), mode=mode)
        return launch_detached(command, working_directory=self._installation.paths.root)
