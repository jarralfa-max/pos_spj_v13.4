"""Durable local evidence staging for offline Losses capture."""

from hashlib import sha256
from pathlib import Path
import shutil

from backend.shared.app_paths import AppPaths


class LocalLossEvidenceStore:
    def __init__(self, paths: AppPaths) -> None:
        self._directory = paths.user_data_dir / "evidence" / "losses"

    def stage(self, *, source_path: Path, evidence_id: str, checksum: str) -> str:
        self._directory.mkdir(parents=True, exist_ok=True)
        suffix = source_path.suffix.lower()
        target = self._directory / f"{evidence_id}{suffix}"
        temporary = target.with_suffix(target.suffix + ".staging")
        shutil.copyfile(source_path, temporary)
        if self._checksum(temporary) != checksum:
            temporary.unlink(missing_ok=True)
            raise IOError("Staged loss evidence checksum mismatch")
        temporary.replace(target)
        return target.resolve().as_uri()

    @staticmethod
    def _checksum(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
