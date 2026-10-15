"""Application path resolver for desktop, service, and packaged .exe runs.

ONE resolution for every consumer of the database file: the desktop
(`frontend/desktop/app.py`), the connection pool
(`backend/infrastructure/db/connection.py`), the future API
(`backend/infrastructure/db/database.py`), the backup/updater and the local
WhatsApp service (`whatsapp_service/config/settings.py`). None of them builds
the path on its own any more.

Two layouts:

* ``source`` — a source checkout (not frozen, no `install_config.json`). The
  development layout is kept exactly as it always was: database in
  `<package>/data/spj_pos_database.db`, logs in `<package>/logs`; other user
  data (secrets fallback, product images, media) in
  `%APPDATA%/SPJ/SPJ ERP POS`. The refactor runbooks reset this database by
  that path, so it does not move.
* ``installed`` — a PyInstaller build, normally installed by the Windows
  installer, which writes `install_config.json` beside the executable. The
  installation directory is read-only; every writable file lives in the data
  root chosen at install time:

    - ``machine`` scope → `%PROGRAMDATA%/SPJ/SPJ ERP POS` (shared by every
      Windows user of the station; the installer grants them modify rights);
    - ``user`` scope → `%LOCALAPPDATA%/SPJ/SPJ ERP POS` (not roaming: a
      SQLite file must not travel with a roaming profile).

  The database is `<data>/db/spj_pos_database.db`. A database left in an
  older location is moved there ONCE, with backup and verification, by
  `backend/infrastructure/db/database_relocation.py` — never by changing this
  path and starting on an empty file.

`SPJ_APP_DATA_DIR` and `SPJ_DB_PATH` override the data root and the database
file for tests, CI self-tests and support work.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys

from backend.shared.install_config import DATA_SCOPE_MACHINE, InstallConfig

DATABASE_FILENAME = "spj_pos_database.db"
LAYOUT_SOURCE = "source"
LAYOUT_INSTALLED = "installed"


@dataclass(frozen=True)
class AppPaths:
    """Resolve SPJ filesystem paths without relying on the process cwd.

    `base_dir` points to the installed executable directory or source checkout.
    `data_dir` points to a writable data location for SQLite, backups, logs,
    updater downloads, and other persistent files.
    `resource_dir` points to read-only bundled artwork and other resources,
    which may be extracted separately from the installed executable.
    `layout` and `install_config` are derived from the environment when not
    injected.
    """

    app_name: str = "SPJ ERP POS"
    company_name: str = "SPJ"
    base_dir: Path | None = None
    data_dir: Path | None = None
    resource_dir: Path | None = None
    layout: str | None = None
    install_config: InstallConfig | None = None
    database_file: Path | None = None
    installer_cache_override: Path | None = None

    @classmethod
    def from_environment(cls) -> "AppPaths":
        base = _default_base_dir()
        config = InstallConfig.load(base)
        layout = _detect_layout(config)
        return cls(
            base_dir=base,
            data_dir=_default_data_dir(cls.company_name, cls.app_name, layout, config),
            resource_dir=_default_resource_dir(),
            layout=layout,
            install_config=config,
        )

    @classmethod
    def for_installation(
        cls, install_dir: Path, *, data_dir: Path | None = None,
        installer_cache: Path | None = None,
    ) -> "AppPaths":
        """Paths of an installation seen from OUTSIDE it — the external
        updater runs from a temporary copy, so `sys.executable` says nothing
        about where SPJ is installed."""
        install_dir = Path(install_dir)
        config = InstallConfig.load(install_dir)
        layout = (LAYOUT_INSTALLED if config is not None or (install_dir / "SPJ.exe").exists()
                  else LAYOUT_SOURCE)
        return cls(
            base_dir=install_dir,
            data_dir=data_dir or _default_data_dir(cls.company_name, cls.app_name, layout, config),
            resource_dir=install_dir,
            layout=layout,
            install_config=config,
            installer_cache_override=installer_cache,
        )

    @property
    def effective_layout(self) -> str:
        return self.layout or _detect_layout(self.install_config)

    @property
    def is_installed(self) -> bool:
        return self.effective_layout == LAYOUT_INSTALLED

    @property
    def root(self) -> Path:
        return (self.base_dir or _default_base_dir()).resolve()

    @property
    def resource_root(self) -> Path:
        """Read-only bundle root, with explicit paths taking precedence.

        An injected base directory describes a complete installation unless
        a separate resource directory is also supplied.
        """
        return (self.resource_dir or self.base_dir or _default_resource_dir()).resolve()

    @property
    def user_data_dir(self) -> Path:
        return (self.data_dir or _default_data_dir(
            self.company_name, self.app_name, self.effective_layout, self.install_config,
        )).resolve()

    @property
    def database_dir(self) -> Path:
        return self.database_path.parent

    @property
    def database_path(self) -> Path:
        """THE database file. See the module docstring for the two layouts."""
        if self.database_file is not None:
            return Path(self.database_file).resolve()
        override = os.environ.get("SPJ_DB_PATH")
        if override:
            return Path(override).expanduser().resolve()
        if self.is_installed:
            return self.user_data_dir / "db" / DATABASE_FILENAME
        return self.source_database_path

    @property
    def source_database_path(self) -> Path:
        """Where a source checkout keeps its database (`<package>/data`)."""
        return self.root / "data" / DATABASE_FILENAME

    @property
    def instance_lock_path(self) -> Path:
        """Held by whoever has the database open: the desktop, the external
        updater, the relocation. Next to the file it protects."""
        database = self.database_path
        return database.with_name(database.name + ".lock")

    @property
    def backups_dir(self) -> Path:
        return self.user_data_dir / "backups"

    @property
    def logs_dir(self) -> Path:
        if self.is_installed:
            return self.user_data_dir / "logs"
        return self.root / "logs"

    @property
    def product_images_dir(self) -> Path:
        return self.user_data_dir / "imagenes_productos"

    @property
    def display_media_dir(self) -> Path:
        """Imágenes y videos de la pantalla del cliente (registro `display_media`)."""
        return self.user_data_dir / "media" / "pantalla_cliente"

    @property
    def whatsapp_data_dir(self) -> Path:
        """Conversaciones del servicio WhatsApp local (si se instaló)."""
        return self.user_data_dir / "whatsapp"

    @property
    def updater_dir(self) -> Path:
        return self.user_data_dir / "updater"

    @property
    def downloads_dir(self) -> Path:
        return self.updater_dir / "downloads"

    @property
    def manifests_dir(self) -> Path:
        return self.updater_dir / "manifests"

    @property
    def installer_cache_dir(self) -> Path:
        """Installers kept for rollback (the installed version and the previous).

        On an installed Windows station it is MACHINE-wide and written ONLY by
        the elevated installer (it copies itself there), whatever the data
        scope, and it is NOT under the data root (whose ACL lets every user
        modify files): a user must not be able to replace an executable that a
        rollback would later run with administrator rights. The updater only
        reads it, and checks each file against the admin-written
        `installers.json` before running it.
        """
        if self.installer_cache_override is not None:
            return Path(self.installer_cache_override).resolve()
        if (sys.platform.startswith("win") and self.is_installed
                and not os.environ.get("SPJ_APP_DATA_DIR")):
            base = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
            return base / self.company_name / "Installers" / self.app_name
        return self.updater_dir / "installers"

    @property
    def updater_lock_path(self) -> Path:
        """Held by the external updater while it runs."""
        return self.updater_dir / "updater.lock"

    @property
    def update_job_path(self) -> Path:
        return self.updater_dir / "update_job.json"

    @property
    def station_settings_path(self) -> Path:
        """Per-station updater settings that must survive a database restore."""
        return self.updater_dir / "station_settings.json"

    def ensure_directories(self) -> "AppPaths":
        """Create the writable folders — only those inside the data root.

        In a source checkout the database and logs folders live in the code
        tree (`<package>/data`, `<package>/logs`); the desktop start creates
        them there as it always did. This method never writes outside the data
        root, so it can never touch an installation or bundle folder.
        """
        data_root = self.user_data_dir
        for path in (
            data_root,
            self.database_dir,
            self.backups_dir,
            self.logs_dir,
            self.product_images_dir,
            self.display_media_dir,
            self.downloads_dir,
            self.manifests_dir,
        ):
            if path == data_root or data_root in path.parents:
                path.mkdir(parents=True, exist_ok=True)
        return self


def _detect_layout(config: InstallConfig | None) -> str:
    if config is not None or getattr(sys, "frozen", False):
        return LAYOUT_INSTALLED
    return LAYOUT_SOURCE


def _default_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _default_resource_dir() -> Path:
    bundle_directory = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and bundle_directory:
        return Path(bundle_directory)
    return _default_base_dir()


def _default_data_dir(
    company_name: str, app_name: str, layout: str = LAYOUT_SOURCE,
    config: InstallConfig | None = None,
) -> Path:
    override = os.environ.get("SPJ_APP_DATA_DIR")
    if override:
        return Path(override).expanduser()

    if sys.platform.startswith("win"):
        if layout == LAYOUT_INSTALLED:
            if config is not None and config.data_scope == DATA_SCOPE_MACHINE:
                base = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
            else:
                base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            return base / company_name / app_name
        # Source checkout: unchanged since before the installer existed —
        # secrets fallback, product images and media already live here.
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / company_name / app_name

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / company_name / app_name

    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / company_name.lower().replace(" ", "-") / app_name.lower().replace(" ", "-")
