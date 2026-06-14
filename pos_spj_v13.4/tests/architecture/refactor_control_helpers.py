from __future__ import annotations

import json
import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parent
REFACTOR_DIR = PACKAGE_ROOT / "docs" / "refactor"
MODULES_DIR = REFACTOR_DIR / "modules"
CONTROL_FILE_NAMES = {
    "MASTER_REFACTOR_STATE.md",
    "MODULE_QUEUE.md",
    "CURRENT_MODULE.md",
    "GLOBAL_VIOLATIONS.md",
    "UUIDV7_CUTOVER_REPORT.md",
    "refactor_state.json",
}
REQUIRED_CONTROL_PATHS = [
    REFACTOR_DIR / "MASTER_REFACTOR_STATE.md",
    REFACTOR_DIR / "MODULE_QUEUE.md",
    REFACTOR_DIR / "CURRENT_MODULE.md",
    REFACTOR_DIR / "GLOBAL_VIOLATIONS.md",
    REFACTOR_DIR / "UUIDV7_CUTOVER_REPORT.md",
    REFACTOR_DIR / "refactor_state.json",
    MODULES_DIR / "README.md",
]
ALLOWED_STATES = {
    "PENDING",
    "AUDIT",
    "PROTECTION",
    "IMPLEMENTATION",
    "LEGACY_REMOVAL",
    "INTEGRATION",
    "VALIDATION",
    "BLOCKED",
    "DONE",
}


def load_refactor_state() -> dict:
    return json.loads((REFACTOR_DIR / "refactor_state.json").read_text(encoding="utf-8"))


def parse_queue_modules() -> dict[str, str]:
    content = (REFACTOR_DIR / "MODULE_QUEUE.md").read_text(encoding="utf-8")
    rows: dict[str, str] = {}
    for line in content.splitlines():
        match = re.match(r"^\|\s*\d+\s*\|\s*([A-Z0-9_]+)\s*\|.*\|\s*([A-Z_]+)\s*\|$", line)
        if match:
            rows[match.group(1)] = match.group(2)
    return rows


def parse_current_module_code() -> str:
    content = (REFACTOR_DIR / "CURRENT_MODULE.md").read_text(encoding="utf-8")
    match = re.search(r"## Código\s*\n\s*```text\s*\n([^\n]+)\n```", content)
    assert match, "CURRENT_MODULE.md must include a Código fenced text block"
    return match.group(1).strip()
