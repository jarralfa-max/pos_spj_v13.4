"""A checked-in merge conflict must fail before the runtime can be released."""

from pathlib import Path
import re
import subprocess

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CONFLICT_MARKER = re.compile(
    rb"^(?:<{7}(?: [^\r\n]*)?|={7}|>{7}(?: [^\r\n]*)?|\|{7}(?: [^\r\n]*)?)\r?$",
    re.MULTILINE,
)


@pytest.mark.parametrize("marker", [b"<" * 7 + b" HEAD", b"=" * 7, b">" * 7 + b" branch", b"|" * 7 + b" base"])
def test_conflict_scanner_detects_merge_and_diff3_markers(marker):
    assert CONFLICT_MARKER.search(b"before\r\n" + marker + b"\r\nafter\r\n")


def test_conflict_scanner_allows_documentation_dividers():
    assert not CONFLICT_MARKER.search(b"=" * 50 + b"\n")
    assert not CONFLICT_MARKER.search(b"    return left >= right\n")


def test_no_git_conflict_markers_in_tracked_text_files():
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    ).stdout
    violations = []
    for relative_name in tracked.split(b"\0"):
        if not relative_name:
            continue
        relative_path = relative_name.decode("utf-8")
        path = REPOSITORY_ROOT / relative_path
        # Deleted paths remain in the index until staged; they have no runtime.
        if not path.is_file():
            continue
        content = path.read_bytes()
        if b"\0" in content:
            continue
        for match in CONFLICT_MARKER.finditer(content):
            line = content.count(b"\n", 0, match.start()) + 1
            violations.append(f"{relative_path}:{line}")
    assert not violations, "Unresolved Git conflicts:\n" + "\n".join(violations)
