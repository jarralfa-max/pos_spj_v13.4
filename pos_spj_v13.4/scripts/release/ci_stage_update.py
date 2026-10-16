"""Stage an update job for an INSTALLED copy and print the updater command.

Test harness (local and Windows CI) for the real end-to-end path:
installer → `spj_updater.exe` → elevated/per-user Inno run → self-test →
COMPLETED or rollback. It writes the same `update_job.json` the in-app
scheduler (`ScheduleUpdateInstallUseCase`) writes once a download is
verified; manifest signing is out of scope here (it is covered by
`tests/integration/software_distribution`).

    python ci_stage_update.py --install-dir "C:\\Program Files\\SPJ\\SPJ ERP POS" \
        --installer build\\windows\\release\\SPJ-Setup-13.4.1-x64.exe \
        --from-version 13.4.0 --to-version 13.4.1 [--data-dir ...]

Prints one JSON line with `job_path` and `command` (the updater copied to a
temporary folder, as the desktop does).
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from _release_common import sha256_file

from backend.domain.software_distribution.update_job import UpdateJob
from backend.infrastructure.updater.update_job_store import UpdateJobStore
from backend.shared.app_paths import AppPaths
from backend.shared.ids import new_uuid


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-dir", required=True, type=Path)
    parser.add_argument("--installer", required=True, type=Path)
    parser.add_argument("--from-version", required=True)
    parser.add_argument("--to-version", required=True)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--installer-cache", type=Path,
                        help="Defaults to the machine cache the installer writes "
                             "(%%PROGRAMDATA%%/SPJ/Installers/SPJ ERP POS), even when "
                             "SPJ_APP_DATA_DIR redirects the data for a test.")
    args = parser.parse_args(argv)
    cache = args.installer_cache or (
        Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "SPJ" / "Installers" / "SPJ ERP POS")
    paths = AppPaths.for_installation(args.install_dir, data_dir=args.data_dir,
                                      installer_cache=cache)
    installer = args.installer.resolve()
    job = UpdateJob(
        job_id=new_uuid(), operation_id=new_uuid(), from_version=args.from_version,
        to_version=args.to_version, channel="stable", installer_path=str(installer),
        installer_sha256=sha256_file(installer), installer_size=installer.stat().st_size,
        database_path=str(paths.database_path), workstation_id="ci", branch_id="",
        requested_by="ci", created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    store = UpdateJobStore(paths.update_job_path)
    store.save(job)
    private = Path(tempfile.mkdtemp(prefix="spj-updater-"))
    updater = private / "spj_updater.exe"
    shutil.copy2(paths.root / "spj_updater.exe", updater)
    command = [str(updater), "--mode", "install", "--job", str(store.path), "--wait-pid", "0",
               "--install-dir", str(paths.root), "--data-dir", str(paths.user_data_dir),
               "--installer-cache", str(paths.installer_cache_dir), "--headless",
               "--no-relaunch"]
    print(json.dumps({"job_path": str(store.path), "database": str(paths.database_path),
                      "command": command}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
