"""Per-user installations (/CURRENTUSER): recorded in install_config.json and
updated WITHOUT elevation; machine installations keep going through UAC."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.shared.install_config import InstallConfig, InstallConfigError


def test_install_mode_round_trips_and_defaults_to_admin():
    assert InstallConfig.from_mapping({"format": "spj-install/1"}).install_mode == "admin"
    config = InstallConfig.from_mapping({"format": "spj-install/1", "install_mode": "user"})
    assert InstallConfig.from_mapping(config.to_mapping()).install_mode == "user"
    with pytest.raises(InstallConfigError):
        InstallConfig.from_mapping({"format": "spj-install/1", "install_mode": "root"})


@pytest.mark.parametrize("mode, elevated, extra", [("admin", True, []), ("user", False, ["/CURRENTUSER"])])
def test_updater_elevates_only_machine_installations(tmp_path, monkeypatch, mode, elevated, extra):
    from backend.domain.software_distribution.update_job import UpdateJob
    from backend.infrastructure.updater import updater_main
    from backend.infrastructure.updater.update_job_store import UpdateJobStore
    from backend.shared.app_paths import AppPaths

    install = tmp_path / "SPJ"
    install.mkdir()
    (install / "install_config.json").write_text(json.dumps(
        {"format": "spj-install/1", "data_scope": "user", "install_mode": mode}), encoding="utf-8")
    paths = AppPaths.for_installation(install, data_dir=tmp_path / "data")
    job = UpdateJob(job_id="j", operation_id="o", from_version="1.0.0", to_version="1.0.1",
                    channel="stable", installer_path=str(tmp_path / "x.exe"),
                    installer_sha256="a" * 64, installer_size=1,
                    database_path=str(tmp_path / "db.sqlite"), workstation_id="w",
                    branch_id="b", requested_by="u")
    transaction = updater_main.build_transaction(
        paths, job, store=UpdateJobStore(tmp_path / "job.json"), require_signature=False)
    assert transaction._runner._elevate is elevated
    arguments = transaction._arguments(job, str(tmp_path / "x.exe"))
    assert arguments[-len(extra):] == extra if extra else "/CURRENTUSER" not in arguments
    assert "/SILENT" in arguments and Path(arguments[5].split("=", 1)[1]).parent == paths.logs_dir
