"""SDLC-INST-001 — `update_job.json` vive en una carpeta que cualquier usuario de
Windows puede modificar, así que nada de lo que dice decide qué instalador corre
elevado. El hash sale del manifiesto firmado, verificado en el actualizador."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from backend.application.software_updates.update_transaction import (
    TransactionTimeouts,
    UpdateTransaction,
)
from backend.domain.software_distribution.update_job import UpdateJob, UpdateJobState
from backend.infrastructure.db.sqlite_backup import SQLiteBackupService
from backend.infrastructure.runtime.instance_lock import InstanceLock
from backend.infrastructure.updater import updater_main
from backend.infrastructure.updater.installer_trust import (
    AuthenticodeResult,
    AuthenticodeVerifier,
    CachedInstaller,
    InstallerTrustError,
)
from backend.infrastructure.updater.package_integrity import (
    PackageIntegrityError,
    file_sha256,
    verify_file,
)
from backend.infrastructure.updater.release_authority import (
    DevelopmentReleaseAuthority,
    RefusedReleaseAuthority,
    ReleaseNotAuthorizedError,
    SignedReleaseAuthority,
)
from backend.infrastructure.updater.update_job_store import UpdateJobStore
from backend.infrastructure.updater.update_manifest import (
    ManifestSignatureError,
    SignedManifestReader,
    TrustedKeyring,
)
from backend.shared.app_paths import LAYOUT_INSTALLED, AppPaths
from backend.shared.install_config import InstallConfig

from ._helpers import make_wal_database, new_key, reader_for, release_payload, signed_bytes

PACKAGE = b"MZ legitimate installer" + b"\x00" * 64
EVIL = b"MZ evil installer"


def _job(tmp_path, installer: Path, manifest: bytes, **changes) -> UpdateJob:
    values = dict(
        job_id="job-1", operation_id="op-1", from_version="13.4.0", to_version="13.5.0",
        channel="stable", installer_path=str(installer), installer_sha256=file_sha256(installer),
        installer_size=installer.stat().st_size, database_path=str(tmp_path / "db.sqlite"),
        workstation_id="ws", branch_id="br", requested_by="admin",
        signed_manifest=manifest.decode("utf-8"))
    values.update(changes)
    return UpdateJob(**values)


@pytest.fixture()
def release(tmp_path):
    private, trusted = new_key()
    installer = tmp_path / "downloads" / "SPJ-Setup-13.5.0-x64.exe"
    installer.parent.mkdir()
    installer.write_bytes(PACKAGE)
    manifest = signed_bytes(private, trusted.key_id, release_payload(package=PACKAGE))
    authority = SignedReleaseAuthority(reader_for(trusted), installed_version="13.4.0",
                                       stage_parent=tmp_path / "private")
    (tmp_path / "private").mkdir()
    return {"private": private, "trusted": trusted, "installer": installer,
            "manifest": manifest, "authority": authority, "tmp": tmp_path}


def test_signed_release_is_staged_in_a_private_copy(release):
    job = _job(release["tmp"], release["installer"], release["manifest"])
    staged = release["authority"].authorize(job)
    assert staged != release["installer"]
    assert staged.parent.parent == release["tmp"] / "private"
    assert staged.read_bytes() == PACKAGE
    # Cambiar el archivo de la carpeta común después ya no alcanza a lo que corre.
    release["installer"].write_bytes(EVIL)
    assert staged.read_bytes() == PACKAGE

    release["authority"].discard()
    assert not staged.exists()


def test_forged_hash_in_the_job_does_not_authorize_another_installer(release):
    # El ataque de SDLC-INST-001: se sustituye el exe y se reescribe el hash del job.
    release["installer"].write_bytes(EVIL)
    job = _job(release["tmp"], release["installer"], release["manifest"])
    assert job.installer_sha256 == hashlib.sha256(EVIL).hexdigest()
    with pytest.raises(PackageIntegrityError):
        release["authority"].authorize(job)


def test_altered_manifest_is_refused(release):
    envelope = json.loads(release["manifest"])
    envelope["payload"]["artifact"]["sha256"] = hashlib.sha256(EVIL).hexdigest()
    forged = json.dumps(envelope).encode("utf-8")
    with pytest.raises(ManifestSignatureError):
        release["authority"].authorize(_job(release["tmp"], release["installer"], forged))


def test_manifest_signed_by_an_unknown_key_is_refused(release):
    other_private, other = new_key("otra-llave")
    forged = signed_bytes(other_private, other.key_id, release_payload(package=PACKAGE))
    with pytest.raises(ManifestSignatureError):
        release["authority"].authorize(_job(release["tmp"], release["installer"], forged))


def test_job_without_signed_manifest_is_refused(release):
    job = _job(release["tmp"], release["installer"], b"")
    with pytest.raises(ReleaseNotAuthorizedError):
        release["authority"].authorize(job)


def test_empty_keyring_refuses(release):
    authority = SignedReleaseAuthority(SignedManifestReader(TrustedKeyring(())),
                                       installed_version="13.4.0")
    with pytest.raises(ManifestSignatureError):
        authority.authorize(_job(release["tmp"], release["installer"], release["manifest"]))


def test_job_cannot_announce_another_version_than_the_manifest(release):
    job = _job(release["tmp"], release["installer"], release["manifest"], to_version="13.9.0")
    with pytest.raises(ReleaseNotAuthorizedError):
        release["authority"].authorize(job)


@pytest.mark.parametrize("installed", ["13.5.0", "14.0.0"])
def test_validly_signed_old_release_cannot_downgrade(release, installed):
    authority = SignedReleaseAuthority(reader_for(release["trusted"]), installed_version=installed)
    with pytest.raises(ReleaseNotAuthorizedError):
        authority.authorize(_job(release["tmp"], release["installer"], release["manifest"]))


def test_development_authority_checks_against_the_job(release):
    job = _job(release["tmp"], release["installer"], b"")
    assert DevelopmentReleaseAuthority(verify_file).authorize(job) == release["installer"]
    release["installer"].write_bytes(EVIL)
    with pytest.raises(PackageIntegrityError):
        DevelopmentReleaseAuthority(verify_file).authorize(job)


# ── la transacción ─────────────────────────────────────────────────────────
class Installer:
    def __init__(self) -> None:
        self.runs: list[str] = []

    def run(self, installer, arguments, *, timeout_seconds):
        self.runs.append(str(installer))
        return 0


class SelfTest:
    def run(self, *, timeout_seconds):
        return type("Report", (), {"ok": True, "version": "13.5.0", "schema_version": 1,
                                   "detail": ""})()


class Allow:
    def check(self, installer):
        return None


class Cache:
    def __init__(self, entry=None) -> None:
        self.entry = entry

    def installer_for(self, version):
        return self.entry


def _transaction(tmp_path, authority, installer, cache=None) -> UpdateTransaction:
    database = tmp_path / "data" / "db" / "spj.db"
    if not database.exists():
        make_wal_database(database, rows=3).close()
    return UpdateTransaction(
        job_store=UpdateJobStore(tmp_path / "data" / "updater" / "update_job.json"),
        database_lock=InstanceLock(database.with_name(database.name + ".lock")),
        backup=SQLiteBackupService(), backups_dir=tmp_path / "data" / "backups",
        installer_runner=installer,
        installer_arguments=lambda job, path: [], self_test=SelfTest(), trust=Allow(),
        installer_cache=cache or Cache(), release_authority=authority,
        wait_for_exit=lambda pid, timeout: True,
        timeouts=TransactionTimeouts(app_exit_seconds=0.1, lock_seconds=0.1))


def test_forged_job_never_reaches_the_installer(release):
    release["installer"].write_bytes(EVIL)
    job = _job(release["tmp"], release["installer"], release["manifest"],
               database_path=str(release["tmp"] / "data" / "db" / "spj.db"))
    runner = Installer()
    result = _transaction(release["tmp"], release["authority"], runner).run(job, wait_pid=1)
    assert result.state is UpdateJobState.CANCELLED
    assert runner.runs == []


def test_genuine_release_runs_the_private_copy_not_the_shared_file(release):
    job = _job(release["tmp"], release["installer"], release["manifest"],
               database_path=str(release["tmp"] / "data" / "db" / "spj.db"))
    runner = Installer()
    result = _transaction(release["tmp"], release["authority"], runner).run(job, wait_pid=1)
    assert result.state is UpdateJobState.COMPLETED, result.last_detail
    assert len(runner.runs) == 1 and runner.runs[0] != str(release["installer"])


def test_recovery_ignores_the_installer_path_written_in_the_job(release):
    # `recover` parte del job en disco: esa ruta no puede decidir qué corre elevado.
    evil = release["tmp"] / "evil.exe"
    evil.write_bytes(EVIL)
    cached = release["tmp"] / "cache" / "previous.exe"
    cached.parent.mkdir()
    cached.write_bytes(PACKAGE)
    database = release["tmp"] / "data" / "db" / "spj.db"
    job = _job(release["tmp"], release["installer"], release["manifest"],
               database_path=str(database), previous_installer_path=str(evil))
    job = (job.transition(UpdateJobState.WAITING_FOR_APP_EXIT)
           .transition(UpdateJobState.BACKING_UP).transition(UpdateJobState.INSTALLING)
           .transition(UpdateJobState.ROLLING_BACK).transition(UpdateJobState.NEEDS_RECOVERY))
    runner = Installer()
    entry = CachedInstaller("13.4.0", cached, file_sha256(cached))
    transaction = _transaction(release["tmp"], release["authority"], runner, Cache(entry))
    self_test = transaction._self_test
    self_test.run = lambda **kwargs: type(
        "Report", (), {"ok": True, "version": "13.4.0", "schema_version": 1, "detail": ""})()

    result = transaction.recover(job)

    assert result.state is UpdateJobState.RECOVERED
    assert runner.runs == [str(cached)]


# ── Authenticode: el editor esperado ───────────────────────────────────────
GOOD = "CN=SPJ Alimentos, O=SPJ Alimentos, C=MX"


def _signatures(monkeypatch, by_name: dict) -> None:
    monkeypatch.setattr(AuthenticodeVerifier, "inspect", staticmethod(
        lambda path: by_name[Path(path).name]))


def test_installer_signed_by_another_publisher_is_refused(monkeypatch, tmp_path):
    # Antes bastaba cualquier certificado válido: no había editor esperado.
    _signatures(monkeypatch, {"SPJ.exe": AuthenticodeResult(True, GOOD, "Valid"),
                              "setup.exe": AuthenticodeResult(True, "CN=Otro Editor", "Valid")})
    verifier = AuthenticodeVerifier(required=True, reference=tmp_path / "SPJ.exe")
    with pytest.raises(InstallerTrustError, match="editor esperado"):
        verifier.check(tmp_path / "setup.exe")


def test_subject_is_compared_exactly_not_as_a_substring(monkeypatch, tmp_path):
    _signatures(monkeypatch, {"setup.exe": AuthenticodeResult(True, GOOD + " Falso", "Valid")})
    verifier = AuthenticodeVerifier(required=True, expected_subject=GOOD)
    with pytest.raises(InstallerTrustError, match="editor esperado"):
        verifier.check(tmp_path / "setup.exe")


def test_same_publisher_is_accepted(monkeypatch, tmp_path):
    _signatures(monkeypatch, {"SPJ.exe": AuthenticodeResult(True, GOOD, "Valid"),
                              "setup.exe": AuthenticodeResult(True, GOOD, "Valid")})
    verifier = AuthenticodeVerifier(required=True, reference=tmp_path / "SPJ.exe")
    assert verifier.check(tmp_path / "setup.exe").subject == GOOD


def test_unsigned_reference_fails_closed(monkeypatch, tmp_path):
    _signatures(monkeypatch, {"SPJ.exe": AuthenticodeResult(False, "", "NotSigned"),
                              "setup.exe": AuthenticodeResult(True, GOOD, "Valid")})
    verifier = AuthenticodeVerifier(required=True, reference=tmp_path / "SPJ.exe")
    with pytest.raises(InstallerTrustError, match="editor"):
        verifier.check(tmp_path / "setup.exe")


def test_required_without_any_expected_publisher_fails_closed(monkeypatch, tmp_path):
    _signatures(monkeypatch, {"setup.exe": AuthenticodeResult(True, GOOD, "Valid")})
    with pytest.raises(InstallerTrustError, match="editor"):
        AuthenticodeVerifier(required=True).check(tmp_path / "setup.exe")


# ── qué autoridad le toca a cada build ─────────────────────────────────────
def _paths(tmp_path, *, signed: bool | None, mode: str = "admin") -> AppPaths:
    install = tmp_path / "SPJ"
    (install / "_internal").mkdir(parents=True)
    if signed is not None:
        (install / "_internal" / "build_info.json").write_text(json.dumps(
            {"version": "13.4.0", "signed": signed}), encoding="utf-8")
    return AppPaths(base_dir=install, data_dir=tmp_path / "data", resource_dir=install,
                    layout=LAYOUT_INSTALLED, install_config=InstallConfig(install_mode=mode))


def _authority(paths, **kwargs):
    return updater_main.build_release_authority(paths, **{"dev_unsigned": False, **kwargs})


def test_unsigned_elevated_build_cannot_update(tmp_path):
    authority = _authority(_paths(tmp_path, signed=False))
    assert isinstance(authority, RefusedReleaseAuthority)
    with pytest.raises(ReleaseNotAuthorizedError, match="no está firmada"):
        authority.authorize(_job(tmp_path, _exe(tmp_path), b""))


def _exe(tmp_path) -> Path:
    path = tmp_path / "x.exe"
    path.write_bytes(PACKAGE)
    return path


def test_development_mode_is_explicit(tmp_path):
    authority = _authority(_paths(tmp_path, signed=False), dev_unsigned=True)
    assert isinstance(authority, DevelopmentReleaseAuthority)


def test_signed_build_ignores_the_development_flag(tmp_path):
    authority = _authority(_paths(tmp_path, signed=True), dev_unsigned=True)
    assert isinstance(authority, SignedReleaseAuthority)


def test_per_user_install_is_not_elevated_but_still_needs_the_manifest(tmp_path):
    authority = _authority(_paths(tmp_path, signed=False, mode="user"))
    assert isinstance(authority, SignedReleaseAuthority)


def test_signature_requirement_comes_from_the_installed_build_not_the_command_line(tmp_path):
    paths = _paths(tmp_path, signed=True)
    job = _job(tmp_path, _exe(tmp_path), b"")
    transaction = updater_main.build_transaction(
        paths, job, store=UpdateJobStore(tmp_path / "job.json"), require_signature=False)
    assert transaction._trust.required is True


def test_launcher_passes_the_development_flag_only_when_asked(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from backend.infrastructure.updater.update_launcher import ExternalUpdaterLauncher

    updater = tmp_path / "SPJ" / "spj_updater.exe"
    paths = _paths(tmp_path, signed=False)
    updater.write_bytes(b"MZ")
    installation = SimpleNamespace(paths=paths, updater_command=[str(updater)],
                                   build=SimpleNamespace(signed=False))
    launcher = ExternalUpdaterLauncher(installation)

    monkeypatch.delenv("SPJ_UPDATER_DEV_MODE", raising=False)
    assert "--dev-unsigned" not in launcher.command(job_path=tmp_path / "j.json", wait_pid=1)
    monkeypatch.setenv("SPJ_UPDATER_DEV_MODE", "1")
    assert "--dev-unsigned" in launcher.command(job_path=tmp_path / "j.json", wait_pid=1)


def test_scheduled_job_carries_the_signed_manifest():
    """El manifiesto viaja dentro del job: se autentica solo, sin importar dónde
    esté guardado el job."""
    fields = UpdateJob.__dataclass_fields__
    assert "signed_manifest" in fields
    job = UpdateJob.from_dict({
        "job_id": "j", "operation_id": "o", "from_version": "1.0.0", "to_version": "1.0.1",
        "channel": "stable", "installer_path": "x", "installer_sha256": "a", "installer_size": 1,
        "database_path": "d", "workstation_id": "w", "branch_id": "b", "requested_by": "u",
        "state": "STAGED", "history": [], "signed_manifest": "{}"})
    assert job.signed_manifest == "{}"
    assert job.to_dict()["signed_manifest"] == "{}"

