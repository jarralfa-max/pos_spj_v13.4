"""Application path resolver for desktop, service, and packaged .exe runs."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys


@dataclass(frozen=True)
class AppPaths:
    """Resolve SPJ filesystem paths without relying on the process cwd.

    `base_dir` points to the installed application bundle or source checkout.
    `data_dir` points to a writable user-data location for SQLite, backups,
    logs, updater downloads, and other persistent files.
    """

    app_name: str = "SPJ ERP POS"
    company_name: str = "SPJ"
    base_dir: Path | None = None
    data_dir: Path | None = None

    @classmethod
    def from_environment(cls) -> "AppPaths":
        return cls(
            base_dir=_default_base_dir(),
            data_dir=_default_data_dir(cls.company_name, cls.app_name),
        )

    @property
    def root(self) -> Path:
        return (self.base_dir or _default_base_dir()).resolve()

    @property
    def user_data_dir(self) -> Path:
        return (self.data_dir or _default_data_dir(self.company_name, self.app_name)).resolve()

    @property
    def database_dir(self) -> Path:
        return self.user_data_dir / "db"

    @property
    def backups_dir(self) -> Path:
        return self.user_data_dir / "backups"

    @property
    def logs_dir(self) -> Path:
        return self.user_data_dir / "logs"

    @property
    def updater_dir(self) -> Path:
        return self.user_data_dir / "updater"

    @property
    def downloads_dir(self) -> Path:
        return self.updater_dir / "downloads"

    @property
    def manifests_dir(self) -> Path:
        return self.updater_dir / "manifests"

    def sqlite_database_path(self, filename: str = "spj.sqlite3") -> Path:
        return self.database_dir / filename

    def ensure_directories(self) -> "AppPaths":
        for path in (
            self.user_data_dir,
            self.database_dir,
            self.backups_dir,
            self.logs_dir,
            self.downloads_dir,
            self.manifests_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        return self


def _default_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _default_data_dir(company_name: str, app_name: str) -> Path:
    override = os.environ.get("SPJ_APP_DATA_DIR")
    if override:
        return Path(override).expanduser()

    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / company_name / app_name

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / company_name / app_name

    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / company_name.lower().replace(" ", "-") / app_name.lower().replace(" ", "-")
