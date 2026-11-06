"""Which installer may run elevated — decided here, never by `update_job.json`.

The job lives in the data folder, which every Windows user of the station can
modify. So nothing written in it counts as proof: the hash comes from the signed
release manifest, verified in the updater against the embedded keys. The manifest
travels inside the job because it authenticates itself wherever it is stored.

The installer is copied to a private temporary folder and the COPY is checked and
run: verifying the file in the shared folder would leave a window to swap it
between the check and the UAC prompt.

`DevelopmentReleaseAuthority` is the old job-based check, for unsigned builds that
ask for it explicitly (`--dev-unsigned`); `updater_main` never uses it on a signed
build. `RefusedReleaseAuthority` is what an unsigned machine-wide build gets
otherwise.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
from typing import Callable

from backend.domain.software_distribution.semantic_version import SemanticVersion
from backend.domain.software_distribution.update_job import UpdateJob
from backend.infrastructure.updater.package_integrity import verify_file


class ReleaseNotAuthorizedError(RuntimeError):
    pass


class SignedReleaseAuthority:
    def __init__(self, reader, *, installed_version: str,
                 verify: Callable[[Path, int, str], None] = verify_file,
                 stage_parent: Path | None = None) -> None:
        self._reader = reader
        self._installed = SemanticVersion.parse(installed_version)
        self._verify = verify
        self._stage_parent = stage_parent
        self._stages: list[Path] = []

    def authorize(self, job: UpdateJob) -> Path:
        if not job.signed_manifest:
            raise ReleaseNotAuthorizedError("La actualización no trae su manifiesto firmado.")
        manifest = self._reader.read(job.signed_manifest.encode("utf-8")).manifest
        if str(manifest.version) != job.to_version:
            raise ReleaseNotAuthorizedError(
                f"El manifiesto firmado es de la versión {manifest.version}, "
                f"no de la {job.to_version}.")
        if not manifest.version > self._installed:
            raise ReleaseNotAuthorizedError(
                f"La versión {manifest.version} no es más nueva que la instalada "
                f"({self._installed}).")
        artifact = manifest.artifact
        stage = Path(tempfile.mkdtemp(prefix="spj-install-", dir=self._stage_parent))
        self._stages.append(stage)
        staged = stage / artifact.file_name
        shutil.copyfile(job.installer_path, staged)
        self._verify(staged, artifact.size, artifact.sha256)
        return staged

    def discard(self) -> None:
        """An installer weighs hundreds of MB: do not leave copies behind."""
        for stage in self._stages:
            shutil.rmtree(stage, ignore_errors=True)
        self._stages.clear()


class DevelopmentReleaseAuthority:
    def __init__(self, verify: Callable[[Path, int, str], None] = verify_file) -> None:
        self._verify = verify

    def authorize(self, job: UpdateJob) -> Path:
        installer = Path(job.installer_path)
        self._verify(installer, job.installer_size, job.installer_sha256)
        return installer

    def discard(self) -> None:
        return None


class RefusedReleaseAuthority:
    def __init__(self, reason: str) -> None:
        self._reason = reason

    def authorize(self, job: UpdateJob) -> Path:
        raise ReleaseNotAuthorizedError(self._reason)

    def discard(self) -> None:
        return None
