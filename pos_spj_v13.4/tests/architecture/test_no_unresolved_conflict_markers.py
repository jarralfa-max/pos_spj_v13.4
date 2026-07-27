"""Prevent committed merge-conflict markers from reaching runtime or documentation."""

from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
EXCLUDED_DIRECTORIES = {".git", ".pytest_cache", "__pycache__"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".db", ".sqlite", ".sqlite3"}


def _tracked_text_files() -> list[Path]:
    files: list[Path] = []
    for path in REPO.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_DIRECTORIES for part in path.parts):
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        files.append(path)
    return files


def test_repository_contains_no_unresolved_merge_conflict_markers():
    offenders: list[str] = []
    for path in _tracked_text_files():
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(content.splitlines(), start=1):
            if line.startswith("<<<<<<<") or line == "=======" or line.startswith(">>>>>>>"):
                offenders.append(f"{path.relative_to(REPO)}:{line_number}: {line}")

    assert not offenders, "Unresolved merge-conflict markers found:\n" + "\n".join(offenders)
