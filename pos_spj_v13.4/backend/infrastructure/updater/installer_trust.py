"""Trust checks on an installer executable before it is run elevated.

1. Authenticode — required whenever the RUNNING build is itself signed
   (`build_info.json` → `"signed": true`, i.e. a production release): an
   installer it elevates must carry a valid signature from the same
   publisher. A development build (unsigned) cannot demand what it does not
   have; it logs the gap instead and relies on the manifest signature + hash.
   The check uses `Get-AuthenticodeSignature`; the file path travels in an
   environment variable and is never interpolated into the script text.

2. Rollback cache — `installers.json`, written by the elevated installer in
   the machine-wide cache, lists each cached installer's SHA-256. A file not
   listed, or whose hash differs, is never run.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys

from backend.infrastructure.updater.package_integrity import file_sha256

INSTALLER_INDEX_FILENAME = "installers.json"

#: The path travels in an environment variable, NOT in the command text:
#: `powershell -Command` concatenates trailing arguments into the script.
_PATH_VARIABLE = "SPJ_AUTHENTICODE_TARGET"
_SIGNATURE_SCRIPT = (
    f"$s = Get-AuthenticodeSignature -LiteralPath $env:{_PATH_VARIABLE}; "
    "[pscustomobject]@{Status=[string]$s.Status;"
    "Subject=[string]$s.SignerCertificate.Subject} | ConvertTo-Json -Compress"
)


class InstallerTrustError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthenticodeResult:
    valid: bool
    subject: str
    status: str


class AuthenticodeVerifier:
    def __init__(self, *, required: bool, expected_subject: str = "") -> None:
        self._required = required
        self._expected_subject = expected_subject

    @property
    def required(self) -> bool:
        return self._required

    def check(self, installer: Path) -> AuthenticodeResult | None:
        """None when not required (development build)."""
        if not self._required:
            return None
        result = self.inspect(installer)
        if not result.valid:
            raise InstallerTrustError(
                f"El instalador {Path(installer).name} no tiene una firma Authenticode válida "
                f"({result.status}). No se ejecutará.")
        if self._expected_subject and self._expected_subject not in result.subject:
            raise InstallerTrustError(
                f"El instalador está firmado por «{result.subject}», no por el editor esperado.")
        return result

    @staticmethod
    def inspect(installer: Path) -> AuthenticodeResult:
        if sys.platform != "win32":
            return AuthenticodeResult(False, "", "NotWindows")
        try:
            environment = dict(os.environ, **{_PATH_VARIABLE: str(Path(installer).resolve())})
            completed = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                 _SIGNATURE_SCRIPT],
                capture_output=True, text=True, timeout=60, check=False, env=environment,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            data = json.loads(completed.stdout.strip() or "{}")
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            return AuthenticodeResult(False, "", f"Error: {exc}")
        status = str(data.get("Status") or "Unknown")
        return AuthenticodeResult(status == "Valid", str(data.get("Subject") or ""), status)


@dataclass(frozen=True)
class CachedInstaller:
    version: str
    path: Path
    sha256: str


class InstallerCache:
    """Read-only view of the machine-wide installer cache."""

    def __init__(self, directory: Path) -> None:
        self._dir = Path(directory)

    def entries(self) -> list[CachedInstaller]:
        index = self._dir / INSTALLER_INDEX_FILENAME
        try:
            data = json.loads(index.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return []
        result = []
        for item in data.get("installers", []) if isinstance(data, dict) else []:
            try:
                name = Path(str(item["file"])).name  # never a path outside the cache
                result.append(CachedInstaller(version=str(item["version"]),
                                              path=self._dir / name,
                                              sha256=str(item["sha256"]).lower()))
            except (KeyError, TypeError):
                continue
        return result

    def installer_for(self, version: str) -> CachedInstaller | None:
        for entry in self.entries():
            if entry.version == version and entry.path.is_file():
                if file_sha256(entry.path) != entry.sha256:
                    raise InstallerTrustError(
                        f"El instalador guardado de la versión {version} fue modificado; "
                        "no se usará para revertir.")
                return entry
        return None
