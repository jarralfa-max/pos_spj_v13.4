"""The external updater's transaction: every failure point leaves either the
previous version running on the previous data, or an explicit recovery
state — never a half-migrated database presented as fine.

The installer and the self-test are fakes; the database, its backup and
restore and the instance lock are real files."""
from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from pathlib import Path

import pytest

from backend.application.software_updates.startup_gate import GateKind, UpdateStartupGate
from backend.application.software_updates.update_transaction import (
    TransactionTimeouts,
    UpdateTransaction,
)
from backend.domain.software_distribution.update_job import UpdateJob, UpdateJobState
from backend.infrastructure.db.sqlite_backup import SQLiteBackupService
from backend.infrastructure.runtime.instance_lock import InstanceLock
from backend.infrastructure.updater.installer_trust import CachedInstaller
from backend.infrastructure.updater.package_integrity import file_sha256, verify_file
from backend.infrastructure.updater.process_control import InstallerNotStartedError
from backend.infrastructure.updater.update_job_store import UpdateJobStore

from ._helpers import count_sales, make_wal_database

PACKAGE = b"new installer"
PREVIOUS = b"previous installer"


@dataclass
class Report:
    ok: bool
    version: str
    schema_version: int | None = 339
    detail: str = ""


class FakeSelfTest:
    def __init__(self, *reports: Report) -> None:
        self.reports = list(reports)
        self.calls = 0

    def run(self, *, timeout_seconds):
        self.calls += 1
        return self.reports.pop(0)


class FakeInstaller:
    """Records runs; the NEW installer can 'migrate' the database (drop rows)
    to prove a later failure restores it."""

    def __init__(self, database: Path, codes: dict, *, migrate: bool = False,
                 not_started: bool = False) -> None:
        self.database = database
        self.codes = codes
        self.migrate = migrate
        self.not_started = not_started
        self.runs: list[str] = []

    def run(self, installer, arguments, *, timeout_seconds):
        name = Path(installer).name
        self.runs.append(name)
        if self.not_started:
            raise InstallerNotStartedError("UAC cancelado")
        if self.migrate and name == "new.exe":
            connection = sqlite3.connect(str(self.database))
            connection.execute("DELETE FROM sales")
            connection.execute("CREATE TABLE added_by_new_version (x)")
            connection.commit()
            connection.close()
        return self.codes.get(name, 0)


class AllowTrust:
    def check(self, installer):
        return None


class Cache:
    def __init__(self, entry: CachedInstaller | None) -> None:
        self.entry = entry

    def installer_for(self, version):
        return self.entry


@pytest.fixture()
def world(tmp_path):
    database = tmp_path / "data" / "db" / "spj_pos_database.db"
    make_wal_database(database, rows=12).close()
    new = tmp_path / "downloads" / "new.exe"
    new.parent.mkdir(parents=True)
    new.write_bytes(PACKAGE)
    previous = tmp_path / "installers" / "previous.exe"
    previous.parent.mkdir(parents=True)
    previous.write_bytes(PREVIOUS)
    store = UpdateJobStore(tmp_path / "data" / "updater" / "update_job.json")
    job = UpdateJob(
        job_id="job-1", operation_id="op-1", from_version="13.4.0", to_version="13.5.0",
        channel="stable", installer_path=str(new), installer_sha256=file_sha256(new),
        installer_size=len(PACKAGE), database_path=str(database), workstation_id="ws",
        branch_id="br", requested_by="admin")
    store.save(job)
    return {"tmp": tmp_path, "db": database, "store": store, "job": job,
            "previous": CachedInstaller("13.4.0", previous, file_sha256(previous))}


def transaction(world, *, installer, self_test, cache_entry="previous", exits=True):
    db = world["db"]
    return UpdateTransaction(
        job_store=world["store"], database_lock=InstanceLock(db.with_name(db.name + ".lock")),
        backup=SQLiteBackupService(), backups_dir=world["tmp"] / "data" / "backups",
        installer_runner=installer, installer_arguments=lambda job, path: ["/SILENT"],
        self_test=self_test, trust=AllowTrust(),
        installer_cache=Cache(world["previous"] if cache_entry == "previous" else None),
        verify_package=verify_file, wait_for_exit=lambda pid, timeout: exits,
        timeouts=TransactionTimeouts(app_exit_seconds=0.1, lock_seconds=0.1),
    )


def states(job):
    return [step.state for step in job.history]


def test_happy_path_backs_up_installs_verifies(world):
    installer = FakeInstaller(world["db"], {})
    result = transaction(world, installer=installer,
                         self_test=FakeSelfTest(Report(True, "13.5.0"))).run(world["job"], wait_pid=1)
    assert result.state is UpdateJobState.COMPLETED
    assert states(result) == [UpdateJobState.WAITING_FOR_APP_EXIT, UpdateJobState.BACKING_UP,
                              UpdateJobState.INSTALLING, UpdateJobState.VERIFYING,
                              UpdateJobState.COMPLETED]
    assert installer.runs == ["new.exe"]
    assert count_sales(Path(result.backup_path)) == 12
    assert world["store"].load().state is UpdateJobState.COMPLETED  # journaled


def test_installer_failure_rolls_back_binaries_without_touching_data(world):
    installer = FakeInstaller(world["db"], {"new.exe": 2})
    result = transaction(world, installer=installer,
                         self_test=FakeSelfTest(Report(True, "13.4.0"))).run(world["job"], wait_pid=1)
    assert result.state is UpdateJobState.ROLLED_BACK
    assert installer.runs == ["new.exe", "previous.exe"]
    assert not result.migrations_may_have_run
    assert count_sales(world["db"]) == 12


def test_failed_migration_restores_the_database_and_previous_version(world):
    installer = FakeInstaller(world["db"], {}, migrate=True)
    self_test = FakeSelfTest(Report(False, "13.5.0", detail="migración 340 falló"),
                             Report(True, "13.4.0"))
    result = transaction(world, installer=installer, self_test=self_test).run(
        world["job"], wait_pid=1)
    assert result.state is UpdateJobState.ROLLED_BACK, result.last_detail
    assert "restauró la base" in result.last_detail
    assert count_sales(world["db"]) == 12
    tables = {r[0] for r in sqlite3.connect(str(world["db"])).execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "added_by_new_version" not in tables
    assert installer.runs == ["new.exe", "previous.exe"]


def test_wrong_version_after_install_is_a_failure(world):
    self_test = FakeSelfTest(Report(True, "13.4.0"), Report(True, "13.4.0"))
    result = transaction(world, installer=FakeInstaller(world["db"], {}),
                         self_test=self_test).run(world["job"], wait_pid=1)
    assert result.state is UpdateJobState.ROLLED_BACK
    assert "reporta la versión" in result.last_detail


def test_failed_rollback_requires_recovery_and_recovery_completes_it(world):
    installer = FakeInstaller(world["db"], {"previous.exe": 1}, migrate=True)
    self_test = FakeSelfTest(Report(False, "13.5.0", detail="boom"))
    result = transaction(world, installer=installer, self_test=self_test).run(
        world["job"], wait_pid=1)
    assert result.state is UpdateJobState.NEEDS_RECOVERY
    assert count_sales(world["db"]) == 12  # data restored even though binaries were not

    gate = UpdateStartupGate(world["store"], InstanceLock(world["tmp"] / "updater.lock")).inspect()
    assert gate.kind is GateKind.NEEDS_RECOVERY

    fixed = FakeInstaller(world["db"], {})
    recovered = transaction(world, installer=fixed,
                            self_test=FakeSelfTest(Report(True, "13.4.0"))).recover(result)
    assert recovered.state is UpdateJobState.RECOVERED
    assert fixed.runs == ["previous.exe"]


def test_no_cached_installer_and_broken_new_version_needs_recovery(world):
    installer = FakeInstaller(world["db"], {}, migrate=True)
    self_test = FakeSelfTest(Report(False, "13.5.0"), Report(False, "13.5.0"))
    result = transaction(world, installer=installer, self_test=self_test,
                         cache_entry=None).run(world["job"], wait_pid=1)
    assert result.state is UpdateJobState.NEEDS_RECOVERY
    assert "No hay instalador guardado" in result.last_detail


@pytest.mark.parametrize("scenario", ["app_still_open", "lock_held", "tampered", "uac_declined"])
def test_nothing_changes_when_the_update_cannot_start(world, scenario):
    installer = FakeInstaller(world["db"], {}, not_started=(scenario == "uac_declined"))
    exits = scenario != "app_still_open"
    holder = None
    if scenario == "lock_held":
        holder = InstanceLock(world["db"].with_name(world["db"].name + ".lock"))
        assert holder.acquire()
    if scenario == "tampered":
        Path(world["job"].installer_path).write_bytes(b"evil installer!")
    try:
        result = transaction(world, installer=installer, self_test=FakeSelfTest(),
                             exits=exits).run(world["job"], wait_pid=1)
    finally:
        if holder:
            holder.release()
    assert result.state is UpdateJobState.CANCELLED
    assert count_sales(world["db"]) == 12
    if scenario != "uac_declined":
        assert installer.runs == []


def test_startup_gate_closes_jobs_interrupted_before_installing(world):
    store, job = world["store"], world["job"]
    store.save(job.transition(UpdateJobState.WAITING_FOR_APP_EXIT))
    gate = UpdateStartupGate(store, InstanceLock(world["tmp"] / "updater.lock")).inspect()
    assert gate.kind is GateKind.CLEAR and store.load().state is UpdateJobState.CANCELLED


def test_startup_gate_reports_interrupted_install_as_recovery(world):
    store, job = world["store"], world["job"]
    store.save(job.transition(UpdateJobState.WAITING_FOR_APP_EXIT)
               .transition(UpdateJobState.BACKING_UP).transition(UpdateJobState.INSTALLING))
    gate = UpdateStartupGate(store, InstanceLock(world["tmp"] / "updater.lock")).inspect()
    assert gate.kind is GateKind.NEEDS_RECOVERY
    assert store.load().state is UpdateJobState.NEEDS_RECOVERY


def test_startup_gate_waits_for_a_live_updater(world):
    store, job = world["store"], world["job"]
    store.save(job.transition(UpdateJobState.WAITING_FOR_APP_EXIT))
    updater = InstanceLock(world["tmp"] / "updater.lock")
    assert updater.acquire()
    try:
        gate = UpdateStartupGate(store, InstanceLock(world["tmp"] / "updater.lock")).inspect()
    finally:
        updater.release()
    assert gate.kind is GateKind.IN_PROGRESS
    assert store.load().state is UpdateJobState.WAITING_FOR_APP_EXIT  # untouched
