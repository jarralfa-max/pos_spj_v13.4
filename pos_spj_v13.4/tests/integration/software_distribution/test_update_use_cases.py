"""In-app update use cases on a temporary database: authorization, trail,
deferral by active operations, maintenance window, offline media and the
startup ingestion of the updater's journal."""
from __future__ import annotations

from datetime import datetime, timezone
import shutil
import sqlite3

import pytest

from backend.application.configuracion.permissions import ConfiguracionPermissions as P
from backend.application.software_updates.installation import SoftwareInstallation
from backend.application.software_updates.use_cases import (
    CancelScheduledUpdateUseCase,
    ChangeUpdateChannelUseCase,
    CheckForUpdatesUseCase,
    DownloadUpdateUseCase,
    GetSoftwareStatusQuery,
    ImportOfflineUpdateUseCase,
    InstallTiming,
    LaunchRequest,
    RecordStationStartUseCase,
    RunScheduledUpdateIfDueUseCase,
    ScheduleUpdateInstallUseCase,
    SetMaintenanceWindowUseCase,
    SoftwareUpdateDependencies,
    SoftwareUpdateError,
    StationContext,
    UpdateDeferredError,
)
from backend.domain.settings.exceptions import ConfigurationPermissionDeniedError
from backend.domain.software_distribution.install_profile import EnabledCapabilities
from backend.domain.software_distribution.release_manifest import TargetPlatform
from backend.domain.software_distribution.semantic_version import SemanticVersion
from backend.domain.software_distribution.update_job import UpdateJobState
from backend.infrastructure.db.repositories.software_updates.station_update_repository import (
    SqliteActiveOperationsProbe,
    SqliteStationUpdateRepository,
)
from backend.infrastructure.db.schema.software_updates_schema import create_software_updates_schema
from backend.infrastructure.updater.update_downloader import UpdateDownloader, verify_package_file
from backend.infrastructure.updater.update_job_store import UpdateJobStore
from backend.shared.app_paths import LAYOUT_INSTALLED, AppPaths
from backend.shared.app_version import BuildMetadata
from backend.shared.install_config import InstallConfig

from ._helpers import HOST, FakeOpener, new_key, reader_for, release_payload, signed_bytes

PACKAGE = b"MZ" + b"\x01" * 2048
ALL = frozenset({P.ACTUALIZACIONES_VIEW, P.ACTUALIZACIONES_ADMINISTRAR, P.ACTUALIZACIONES_CANAL})


class Authorization:
    def __init__(self, granted=ALL) -> None:
        self.granted = set(granted)

    def has_permission(self, user_id, code):
        return code in self.granted

    def require(self, user_id, code):
        if code not in self.granted:
            raise ConfigurationPermissionDeniedError(f"El usuario {user_id} no tiene {code}")


class Audit:
    def __init__(self) -> None:
        self.records = []

    def record(self, **kwargs):
        self.records.append(kwargs)


@pytest.fixture()
def env(tmp_path):
    private, trusted = new_key()
    connection = sqlite3.connect(str(tmp_path / "db.sqlite"))
    connection.row_factory = None
    create_software_updates_schema(connection)
    connection.executescript("""
        CREATE TABLE sales (id TEXT PRIMARY KEY, status TEXT, created_at TEXT);
        CREATE TABLE sale_lines (id TEXT PRIMARY KEY, sale_id TEXT);
        CREATE TABLE cash_shifts (id TEXT PRIMARY KEY, status TEXT);
        CREATE TABLE sales_outbox (id TEXT PRIMARY KEY, status TEXT);
    """)
    paths = AppPaths(base_dir=tmp_path / "app", data_dir=tmp_path / "data",
                     layout=LAYOUT_INSTALLED, install_config=InstallConfig())
    installation = SoftwareInstallation(
        version=SemanticVersion.parse("13.4.0"), platform=TargetPlatform("windows", "x64"),
        build=BuildMetadata("13.4.0", "abc", "", "1", False, False),
        capabilities=EnabledCapabilities.everything(), paths=paths,
        feed_url_template=f"https://{HOST}/{{channel}}/manifest.json",
        allowed_hosts=frozenset({HOST}), default_channel="stable", whatsapp_mode="remote")
    opener = FakeOpener({})
    audit = Audit()

    def deps(granted=ALL, clock=None):
        return SoftwareUpdateDependencies(
            connection=connection, installation=installation,
            station=StationContext("CAJA-01", "branch-1", "user-1"),
            authorization=Authorization(granted),
            repository=SqliteStationUpdateRepository(connection),
            reader=reader_for(trusted),
            downloader=UpdateDownloader(paths.downloads_dir, allowed_hosts=frozenset({HOST}),
                                        opener=opener),
            job_store=UpdateJobStore(paths.update_job_path),
            probe=SqliteActiveOperationsProbe(connection),
            audit=audit, verify_package=verify_package_file, schema_version=lambda: 337,
            clock=clock or datetime.now)

    def publish(channel="stable", **overrides):
        payload = release_payload(package=PACKAGE, channel=channel, **overrides)
        opener.routes[f"https://{HOST}/{channel}/manifest.json"] = (
            signed_bytes(private, trusted.key_id, payload), None, None)
        opener.routes[payload["artifact"]["url"]] = (PACKAGE, None, None)
        return payload

    return {"deps": deps, "publish": publish, "conn": connection, "paths": paths,
            "audit": audit, "opener": opener, "private": private, "trusted": trusted,
            "tmp": tmp_path}


def events(env):
    return [row[0] for row in env["conn"].execute(
        "SELECT event_type FROM software_update_events ORDER BY occurred_at, rowid")]


def _ready(env):
    env["publish"]()
    deps = env["deps"]()
    RecordStationStartUseCase(deps).execute()
    assert CheckForUpdatesUseCase(deps).execute().decision.offered
    DownloadUpdateUseCase(deps).execute()
    return deps


def test_check_download_and_install_now(env):
    deps = _ready(env)
    status = GetSoftwareStatusQuery(deps).execute()
    assert status.available is not None and status.available.downloaded
    request = ScheduleUpdateInstallUseCase(deps).execute(InstallTiming.NOW)
    assert isinstance(request, LaunchRequest)
    assert request.job.state is UpdateJobState.STAGED and request.job.to_version == "13.5.0"
    assert request.job_path == env["paths"].update_job_path
    assert events(env)[-3:] == ["OFFERED", "DOWNLOADED", "SCHEDULED"]
    with pytest.raises(SoftwareUpdateError, match="Ya hay"):
        ScheduleUpdateInstallUseCase(deps).execute(InstallTiming.NOW)


def test_tampered_or_downgrade_manifest_is_recorded_and_not_offered(env):
    payload = env["publish"]()
    raw, _, _ = env["opener"].routes[f"https://{HOST}/stable/manifest.json"]
    env["opener"].routes[f"https://{HOST}/stable/manifest.json"] = (
        raw.replace(b"13.5.0", b"13.9.0"), None, None)
    deps = env["deps"]()
    result = CheckForUpdatesUseCase(deps).execute()
    assert result.decision is None and "rechazado" in result.error
    env["publish"](version="13.3.0", minimum=None)
    result = CheckForUpdatesUseCase(deps).execute()
    assert result.decision.rejected
    assert events(env) == ["REJECTED", "REJECTED"]
    assert GetSoftwareStatusQuery(deps).execute().available is None
    assert payload  # silence linters


def test_active_sale_payment_or_cut_defers_installation(env):
    deps = _ready(env)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    env["conn"].execute("INSERT INTO sales VALUES ('s1','ACTIVE',?)", (now,))
    env["conn"].execute("INSERT INTO sale_lines VALUES ('l1','s1')")
    env["conn"].execute("INSERT INTO sales VALUES ('s2','PAYMENT_PENDING',?)", (now,))
    env["conn"].execute("INSERT INTO cash_shifts VALUES ('c1','COUNTING')")
    env["conn"].execute("INSERT INTO sales VALUES ('old','ACTIVE','2020-01-01T00:00:00+00:00')")
    env["conn"].execute("INSERT INTO sale_lines VALUES ('l2','old')")
    with pytest.raises(UpdateDeferredError) as caught:
        ScheduleUpdateInstallUseCase(deps).execute(InstallTiming.NOW)
    assert len(caught.value.decision.reasons) == 3  # the stale sale does not count
    assert events(env)[-1] == "DEFERRED"
    assert deps.job_store.load() is None


def test_open_shift_and_pending_outbox_do_not_block(env):
    deps = _ready(env)
    env["conn"].execute("INSERT INTO cash_shifts VALUES ('c1','OPEN')")
    env["conn"].execute("INSERT INTO sales_outbox VALUES ('o1','PENDING')")
    request = ScheduleUpdateInstallUseCase(deps).execute(InstallTiming.NOW)
    assert request.warnings  # outbox is reported, not blocking


def test_maintenance_window_schedule_waits_for_window_and_idle_till(env):
    deps = _ready(env)
    with pytest.raises(SoftwareUpdateError, match="ventana"):
        ScheduleUpdateInstallUseCase(deps).execute(InstallTiming.MAINTENANCE_WINDOW)
    SetMaintenanceWindowUseCase(deps).execute("22:00-06:00")
    job = ScheduleUpdateInstallUseCase(deps).execute(InstallTiming.MAINTENANCE_WINDOW)
    assert job.scheduled_window == "22:00-06:00"

    noon = env["deps"](clock=lambda: datetime(2026, 1, 1, 12, 0))
    assert RunScheduledUpdateIfDueUseCase(noon).execute() is None
    night = env["deps"](clock=lambda: datetime(2026, 1, 1, 23, 0))
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    env["conn"].execute("INSERT INTO sales VALUES ('s1','CHECKOUT_PENDING',?)", (now,))
    assert RunScheduledUpdateIfDueUseCase(night).execute() is None  # payment in progress
    env["conn"].execute("UPDATE sales SET status='COMPLETED'")
    assert isinstance(RunScheduledUpdateIfDueUseCase(night).execute(), LaunchRequest)

    CancelScheduledUpdateUseCase(deps).execute()
    assert deps.job_store.load() is None
    assert RunScheduledUpdateIfDueUseCase(night).execute() is None


def test_permissions_separate_view_administer_and_channel(env):
    env["publish"]()
    viewer = env["deps"](granted={P.ACTUALIZACIONES_VIEW})
    assert GetSoftwareStatusQuery(viewer).execute().can_administer is False
    assert CheckForUpdatesUseCase(viewer).execute().decision.offered  # checking is a read
    for action in (lambda: DownloadUpdateUseCase(viewer).execute(),
                   lambda: ScheduleUpdateInstallUseCase(viewer).execute(InstallTiming.NOW),
                   lambda: ChangeUpdateChannelUseCase(viewer).execute("pilot"),
                   lambda: SetMaintenanceWindowUseCase(viewer).execute("01:00-02:00")):
        with pytest.raises(ConfigurationPermissionDeniedError):
            action()
    nobody = env["deps"](granted=set())
    with pytest.raises(ConfigurationPermissionDeniedError):
        GetSoftwareStatusQuery(nobody).execute()


def test_channel_change_is_audited_and_switches_feed(env):
    env["publish"](channel="pilot", version="13.6.0-rc.1")
    deps = env["deps"]()
    RecordStationStartUseCase(deps).execute()
    ChangeUpdateChannelUseCase(deps).execute("pilot")
    assert env["audit"].records[-1]["action"] == "CHANNEL_CHANGED"
    result = CheckForUpdatesUseCase(deps).execute()
    assert str(result.manifest.version) == "13.6.0-rc.1" and result.decision.offered
    assert env["opener"].requests[-1].endswith("/pilot/manifest.json")


def test_offline_package_is_verified_before_import(env, tmp_path):
    media = tmp_path / "usb"
    media.mkdir()
    payload = release_payload(package=PACKAGE, host="not-allowed.example",
                              rollout={"percent": 0, "branch_ids": [], "workstation_ids": []})
    (media / "manifest.json").write_bytes(signed_bytes(env["private"], env["trusted"].key_id,
                                                       payload))
    installer = media / payload["artifact"]["file_name"]
    installer.write_bytes(b"tampered" + PACKAGE)
    deps = env["deps"]()
    with pytest.raises(SoftwareUpdateError, match="no es válido"):
        ImportOfflineUpdateUseCase(deps, shutil.copyfile).execute(media)
    installer.write_bytes(PACKAGE)
    manifest = ImportOfflineUpdateUseCase(deps, shutil.copyfile).execute(media / "manifest.json")
    assert str(manifest.version) == "13.5.0"
    request = ScheduleUpdateInstallUseCase(deps).execute(InstallTiming.NOW)
    assert request.job.offline is True
    assert "OFFLINE_IMPORTED" in events(env)


def test_startup_records_version_and_ingests_the_outcome_once(env):
    deps = _ready(env)
    request = ScheduleUpdateInstallUseCase(deps).execute(InstallTiming.NOW)
    job = (request.job.transition(UpdateJobState.WAITING_FOR_APP_EXIT)
           .transition(UpdateJobState.BACKING_UP).transition(UpdateJobState.INSTALLING)
           .transition(UpdateJobState.VERIFYING)
           .transition(UpdateJobState.COMPLETED, "Versión 13.5.0 instalada"))
    deps.job_store.save(job)
    notice = RecordStationStartUseCase(deps).execute()
    assert notice is not None and "13.5.0" in notice.message
    assert deps.job_store.load() is None  # archived
    assert (deps.job_store.history_dir / "job-1.json").exists() is False
    assert list(deps.job_store.history_dir.glob("*.json"))
    assert events(env).count("INSTALL_COMPLETED") == 1
    assert RecordStationStartUseCase(deps).execute() is None
    row = env["conn"].execute(
        "SELECT installed_version, schema_version, install_profile FROM software_station_settings"
    ).fetchone()
    assert row == ("13.4.0", 337, "erp_full")
