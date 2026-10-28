"""Shared helpers of the release scripts — no application imports beyond the
pure domain/infrastructure modules they validate with."""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parent
DEFAULT_BUILD_DIR = REPO_ROOT / "build" / "windows"

if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))


def read_version() -> str:
    """`VERSION` from backend/shared/app_version.py, read with `ast` (the
    single source; nothing else is edited by hand)."""
    source = (PACKAGE_ROOT / "backend" / "shared" / "app_version.py").read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "VERSION" for t in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit("VERSION no encontrado en app_version.py")


def schema_target() -> int:
    """Station schema the build migrates to — asked to the migration engine.

    Until 2026-10-25 this parsed every `_Migration(...)` in engine.py and did
    `int()` on each id; the PostgreSQL lane (`p001`…, central server only) made
    it crash. The engine owns the rule (`target_schema_version()`), so the
    manifest and the stations can never use different scales.
    """
    from migrations.engine import target_schema_version

    return target_schema_version()


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True,
                              text=True, check=True, timeout=30).stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return os.environ.get("GITHUB_SHA", "")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(command: list[str], **kwargs) -> None:
    print("+", " ".join(str(c) for c in command), flush=True)
    subprocess.run([str(c) for c in command], check=True, **kwargs)
