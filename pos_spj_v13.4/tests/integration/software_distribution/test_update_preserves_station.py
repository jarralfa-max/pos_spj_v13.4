"""SDLC-ARQ-INST-002 — §15 T12: actualización exitosa, fallida y rollback conservan
cola de sincronización, identidad de terminal, ancla de sucursal y permisos, y el
respaldo cubre la configuración de la estación.

El instalador y la autoprueba son dobles; la base (con el esquema real), su
respaldo y restauración, y los archivos de configuración son reales. Lo que se
verifica es el mismo marcador que usa el flujo de instalación en CI.
"""
from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from backend.application.software_updates.update_transaction import (
    TransactionTimeouts,
    UpdateTransaction,
)
from backend.bootstrap.run_database_bootstrap import run_database_bootstrap_sequence
from backend.domain.software_distribution.update_job import UpdateJob, UpdateJobState
from backend.infrastructure.db.sqlite_backup import SQLiteBackupService
from backend.infrastructure.runtime.instance_lock import InstanceLock
from backend.infrastructure.updater.installer_trust import CachedInstaller
from backend.infrastructure.updater.package_integrity import file_sha256, verify_file
from backend.infrastructure.updater.release_authority import DevelopmentReleaseAuthority
from backend.infrastructure.updater.station_config_backup import (
    ConfigBackupError,
    StationConfigBackup,
)
from backend.infrastructure.updater.update_job_store import UpdateJobStore
from backend.shared.app_paths import LAYOUT_INSTALLED, AppPaths
from backend.shared.install_config import InstallConfig

ROOT = Path(__file__).resolve().parents[3]
ANCHOR = "01890000-0000-7000-8000-000000000abc"
ORIGINAL_CONFIG = json.dumps({"format": "spj-install/1", "data_scope": "machine",
                              "profile": "erp_full", "update_channel": "pilot",
                              "allowed_update_hosts": ["updates.spj.test"]})
ORIGINAL_SETTINGS = json.dumps({"workstation": "CAJA-01", "maintenance_window": "22:00-06:00"})


def _marker():
    spec = importlib.util.spec_from_file_location(
        "ci_data_marker", ROOT / "scripts" / "release" / "ci_data_marker.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def station_template(tmp_path_factory):
    """Una base con el esquema real, una sola vez: migrarla tarda."""
    database = tmp_path_factory.mktemp("plantilla") / "spj_pos_database.db"
    result = run_database_bootstrap_sequence(database)
    assert result.success, result.failed_step()
    result.context.conn.close()
    connection = sqlite3.connect(str(database))
    connection.execute("INSERT OR REPLACE INTO configuraciones (clave, valor) VALUES (?, ?)",
                        ("sucursal_instalacion_id", ANCHOR))
    connection.commit()
    connection.close()
    assert _marker().main(["write", str(database)]) == 0
    return database


@dataclass
class Report:
    ok: bool
    version: str
    schema_version: int | None = 353
    detail: str = ""


class SelfTest:
    def __init__(self, *reports: Report) -> None:
        self.reports = list(reports)

    def run(self, *, timeout_seconds):
        return self.reports.pop(0)


class Installer:
    """El instalador nuevo reescribe la configuración; con `damage` además una
    migración destruye lo que la estación no puede perder."""

    def __init__(self, world, *, codes: dict | None = None, damage: bool = False) -> None:
        self.world, self.codes, self.damage = world, codes or {}, damage
        self.runs: list[str] = []

    def run(self, installer, arguments, *, timeout_seconds):
        name = Path(installer).name
        self.runs.append(name)
        if name == "new.exe":
            self.world["install_config"].write_text('{"format": "spj-install/1"}', encoding="utf-8")
            self.world["settings"].write_text("{}", encoding="utf-8")
            if self.damage:
                connection = sqlite3.connect(str(self.world["db"]))
                for sql in ("DELETE FROM replication_envelopes", "DELETE FROM rol_permisos",
                            "DELETE FROM software_station_settings",
                            "DELETE FROM configuraciones WHERE clave='sucursal_instalacion_id'"):
                    connection.execute(sql)
                connection.commit()
                connection.close()
        return self.codes.get(name, 0)


class Allow:
    def check(self, installer):
        return None


class Cache:
    def __init__(self, entry) -> None:
        self.entry = entry

    def installer_for(self, version):
        return self.entry


@pytest.fixture()
def world(tmp_path, station_template):
    install = tmp_path / "SPJ"
    install.mkdir()
    install_config = install / "install_config.json"
    install_config.write_text(ORIGINAL_CONFIG, encoding="utf-8")
    paths = AppPaths(base_dir=install, data_dir=tmp_path / "data", resource_dir=install,
                     layout=LAYOUT_INSTALLED, install_config=InstallConfig(install_mode="user"),
                     database_file=tmp_path / "data" / "db" / "spj_pos_database.db")
    paths.database_path.parent.mkdir(parents=True)
    shutil.copyfile(station_template, paths.database_path)
    settings = paths.station_settings_path
    settings.parent.mkdir(parents=True)
    settings.write_text(ORIGINAL_SETTINGS, encoding="utf-8")
    secrets = paths.user_data_dir / "secrets"
    secrets.mkdir()
    (secrets / "master.key").write_bytes(b"llave")

    new = tmp_path / "downloads" / "new.exe"
    new.parent.mkdir()
    new.write_bytes(b"new installer")
    previous = tmp_path / "installers" / "previous.exe"
    previous.parent.mkdir()
    previous.write_bytes(b"previous installer")
    store = UpdateJobStore(paths.update_job_path)
    job = UpdateJob(
        job_id="job-1", operation_id="op-1", from_version="13.4.0", to_version="13.5.0",
        channel="stable", installer_path=str(new), installer_sha256=file_sha256(new),
        installer_size=new.stat().st_size, database_path=str(paths.database_path),
        workstation_id="CAJA-01", branch_id=ANCHOR, requested_by="admin")
    store.save(job)
    return {"paths": paths, "db": paths.database_path, "store": store, "job": job,
            "install_config": install_config, "settings": settings,
            "previous": CachedInstaller("13.4.0", previous, file_sha256(previous))}


def _transaction(world, *, installer, self_test, per_user=True) -> UpdateTransaction:
    paths, db = world["paths"], world["db"]
    return UpdateTransaction(
        job_store=world["store"], database_lock=InstanceLock(db.with_name(db.name + ".lock")),
        backup=SQLiteBackupService(), backups_dir=paths.backups_dir,
        config_backup=StationConfigBackup(paths, restore_install_config=per_user),
        installer_runner=installer, installer_arguments=lambda job, path: [],
        self_test=self_test, trust=Allow(), installer_cache=Cache(world["previous"]),
        release_authority=DevelopmentReleaseAuthority(verify_file),
        wait_for_exit=lambda pid, timeout: True,
        timeouts=TransactionTimeouts(app_exit_seconds=0.1, lock_seconds=0.1))


def _station_is_intact(world) -> bool:
    return _marker().main(["check", str(world["db"])]) == 0


def test_successful_update_keeps_the_station(world):
    result = _transaction(world, installer=Installer(world),
                          self_test=SelfTest(Report(True, "13.5.0"))).run(world["job"], wait_pid=1)
    assert result.state is UpdateJobState.COMPLETED, result.last_detail
    assert _station_is_intact(world)
    # El respaldo guarda lo que había antes aunque el instalador lo haya reescrito.
    snapshot = Path(result.config_backup_path)
    assert (snapshot / "install_config.json").read_text(encoding="utf-8") == ORIGINAL_CONFIG
    assert (snapshot / "station_settings.json").read_text(encoding="utf-8") == ORIGINAL_SETTINGS


def test_failed_installer_keeps_the_station(world):
    installer = Installer(world, codes={"new.exe": 2})
    result = _transaction(world, installer=installer,
                          self_test=SelfTest(Report(True, "13.4.0"))).run(world["job"], wait_pid=1)
    assert result.state is UpdateJobState.ROLLED_BACK, result.last_detail
    assert installer.runs == ["new.exe", "previous.exe"]
    assert _station_is_intact(world)
    assert world["install_config"].read_text(encoding="utf-8") == ORIGINAL_CONFIG
    assert world["settings"].read_text(encoding="utf-8") == ORIGINAL_SETTINGS


def test_rollback_after_a_destructive_migration_returns_queue_identity_anchor_and_permissions(world):
    installer = Installer(world, damage=True)
    assert not _station_is_intact_after_damage_is_detected(world)
    self_test = SelfTest(Report(False, "13.5.0", detail="migración falló"), Report(True, "13.4.0"))
    result = _transaction(world, installer=installer, self_test=self_test).run(
        world["job"], wait_pid=1)
    assert result.state is UpdateJobState.ROLLED_BACK, result.last_detail
    assert "restauró la base" in result.last_detail
    assert _station_is_intact(world)
    assert world["install_config"].read_text(encoding="utf-8") == ORIGINAL_CONFIG
    assert world["settings"].read_text(encoding="utf-8") == ORIGINAL_SETTINGS


def _station_is_intact_after_damage_is_detected(world) -> bool:
    """El marcador sí nota el daño: sin esto, las pruebas de arriba no valen."""
    copy = world["db"].with_name("copia-marcador.db")
    shutil.copyfile(world["db"], copy)
    connection = sqlite3.connect(str(copy))
    connection.execute("DELETE FROM replication_envelopes")
    connection.commit()
    connection.close()
    intact = _marker().main(["check", str(copy)]) == 0
    copy.unlink()
    return intact


@pytest.mark.parametrize("sql", [
    "DELETE FROM replication_envelopes",
    "DELETE FROM software_station_settings",
    "DELETE FROM rol_permisos",
    "UPDATE configuraciones SET valor='otra' WHERE clave='sucursal_instalacion_id'",
])
def test_marker_notices_each_loss(tmp_path, station_template, sql):
    copy = tmp_path / "copia.db"
    shutil.copyfile(station_template, copy)
    connection = sqlite3.connect(str(copy))
    connection.execute(sql)
    connection.commit()
    connection.close()
    assert _marker().main(["check", str(copy)]) == 1


def test_marked_database_still_starts(tmp_path, station_template):
    # CI corre la autoprueba del programa instalado sobre la base marcada.
    copy = tmp_path / "copia.db"
    shutil.copyfile(station_template, copy)
    result = run_database_bootstrap_sequence(copy)
    assert result.success, result.failed_step()
    result.context.conn.close()
    assert _marker().main(["check", str(copy)]) == 0


def test_recovery_restores_the_configuration_too(world):
    # El instalador previo falla: queda NEEDS_RECOVERY, y algo vuelve a tocar la configuración.
    job = _transaction(world, installer=Installer(world, damage=True, codes={"previous.exe": 1}),
                       self_test=SelfTest(Report(False, "13.5.0", detail="falló"))).run(
        world["job"], wait_pid=1)
    assert job.state is UpdateJobState.NEEDS_RECOVERY
    world["settings"].write_text("{}", encoding="utf-8")

    recovered = _transaction(world, installer=Installer(world),
                             self_test=SelfTest(Report(True, "13.4.0"))).recover(job)

    assert recovered.state is UpdateJobState.RECOVERED, recovered.last_detail
    assert world["settings"].read_text(encoding="utf-8") == ORIGINAL_SETTINGS


# ── el respaldo de configuración ───────────────────────────────────────────
def test_snapshot_never_contains_secrets(world):
    snapshot = StationConfigBackup(world["paths"], restore_install_config=True).create(
        world["paths"].backups_dir, label="pre-update-13.5.0")
    names = {p.name for p in snapshot.rglob("*") if p.is_file()}
    assert names == {"install_config.json", "station_settings.json", "snapshot.json"}


def test_snapshot_failure_cancels_before_touching_anything(world):
    class Broken:
        def create(self, destination_dir, *, label):
            raise OSError("disco lleno")

        def restore(self, snapshot):
            raise AssertionError("no debería restaurar")

    installer = Installer(world)
    transaction = _transaction(world, installer=installer, self_test=SelfTest())
    transaction._config_backup = Broken()
    result = transaction.run(world["job"], wait_pid=1)
    assert result.state is UpdateJobState.CANCELLED
    assert "configuración" in result.last_detail
    assert installer.runs == []


def test_machine_install_never_restores_install_config_from_the_shared_folder(world):
    """`install_config.json` dice de qué hosts se aceptan actualizaciones y la
    carpeta de datos la modifica cualquier usuario: en una instalación de máquina
    el archivo sólo lo escribe el instalador elevado."""
    backup = StationConfigBackup(world["paths"], restore_install_config=False)
    snapshot = backup.create(world["paths"].backups_dir, label="x")
    world["install_config"].write_text("reescrito por el instalador", encoding="utf-8")
    world["settings"].write_text("{}", encoding="utf-8")

    restored = backup.restore(snapshot)

    assert restored == ("station_settings.json",)
    assert world["install_config"].read_text(encoding="utf-8") == "reescrito por el instalador"
    assert world["settings"].read_text(encoding="utf-8") == ORIGINAL_SETTINGS


def test_tampered_snapshot_is_not_restored(world):
    backup = StationConfigBackup(world["paths"], restore_install_config=True)
    snapshot = backup.create(world["paths"].backups_dir, label="x")
    (snapshot / "station_settings.json").write_text('{"alterado": true}', encoding="utf-8")
    world["settings"].write_text("{}", encoding="utf-8")
    with pytest.raises(ConfigBackupError):
        backup.restore(snapshot)
    assert world["settings"].read_text(encoding="utf-8") == "{}"


def test_failed_config_restore_does_not_block_the_station(world):
    """La base y los binarios ya volvieron: la configuración se informa, no deja
    la estación pidiendo una recuperación que no la arreglaría."""
    class Unrestorable(StationConfigBackup):
        def restore(self, snapshot):
            raise ConfigBackupError("respaldo alterado")

    transaction = _transaction(world, installer=Installer(world, codes={"new.exe": 2}),
                               self_test=SelfTest(Report(True, "13.4.0")))
    transaction._config_backup = Unrestorable(world["paths"], restore_install_config=True)
    result = transaction.run(world["job"], wait_pid=1)
    assert result.state is UpdateJobState.ROLLED_BACK
    assert "configuración" in result.last_detail


def test_source_checkout_without_config_files_still_snapshots(tmp_path):
    paths = AppPaths(base_dir=tmp_path / "src", data_dir=tmp_path / "data", layout="source")
    backup = StationConfigBackup(paths, restore_install_config=False)
    snapshot = backup.create(tmp_path / "backups", label="x")
    assert backup.restore(snapshot) == ()


# ── el instalador ──────────────────────────────────────────────────────────
ISS = (ROOT / "installer" / "windows" / "spj_setup.iss").read_text(encoding="utf-8")


def test_uninstall_does_not_delete_the_configuration_by_default():
    assert "[UninstallDelete]" not in ISS
    gated = ISS[ISS.index("procedure PurgeStationConfig"):]
    assert "DeleteFile(ExpandConstant('{app}\\install_config.json'))" in gated
    uninstall = ISS[ISS.index("procedure CurUninstallStepChanged"):]
    assert "if WantsConfigPurge then" in uninstall
    # Fuera de esa rama, ninguna línea borra el archivo o la versión instalada.
    assert "RegDeleteValue" not in uninstall.replace("PurgeStationConfig", "")


def test_uninstall_purge_needs_an_explicit_option():
    block = ISS[ISS.index("function WantsConfigPurge"):ISS.index("procedure PurgeStationConfig")]
    assert "/PURGECONFIG" in block
    assert "MB_DEFBUTTON2" in block  # en pantalla, «No» es la opción por omisión
    assert "UninstallSilent" in block


def test_update_channel_survives_repair_and_reinstall():
    assert "ParamOr('CHANNEL', ExistingConfigValue('update_channel'" in ISS


def test_ci_checks_the_configuration_survives():
    workflow = (ROOT.parent / ".github" / "workflows" / "windows-release.yml").read_text(
        encoding="utf-8")
    assert "station-config-pre-update-" in workflow
    assert "La desinstalacion borro la configuracion" in workflow
