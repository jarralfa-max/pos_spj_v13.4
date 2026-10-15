"""Atomic JSON persistence of the current update job (`update_job.json`).

Written at EVERY state transition by the external updater, so a crash, power
cut or killed process leaves the last reached state on disk for the desktop
to diagnose on its next start. Finished jobs are archived under
`updater/history/<job_id>.json` once the desktop has recorded them in the
database.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from backend.domain.software_distribution.update_job import UpdateJob


class UpdateJobStore:
    def __init__(self, job_path: Path) -> None:
        self._path = Path(job_path)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def history_dir(self) -> Path:
        return self._path.parent / "history"

    def load(self) -> UpdateJob | None:
        if not self._path.exists():
            return None
        data = json.loads(self._path.read_text(encoding="utf-8"))
        return UpdateJob.from_dict(data)

    def save(self, job: UpdateJob) -> UpdateJob:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_name(self._path.name + ".tmp")
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(job.to_dict(), handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self._path)
        return job

    def archive(self, job: UpdateJob) -> Path:
        """Move the finished job out of the way (kept for support)."""
        self.history_dir.mkdir(parents=True, exist_ok=True)
        destination = self.history_dir / f"{job.job_id}.json"
        destination.write_text(json.dumps(job.to_dict(), ensure_ascii=False, indent=2),
                               encoding="utf-8")
        self._path.unlink(missing_ok=True)
        return destination
