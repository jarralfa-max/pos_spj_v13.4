from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parent
BOOTSTRAP_PATH = PACKAGE_ROOT / "tools" / "refactor_control" / "bootstrap_refactor_state.py"


def load_bootstrap_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("bootstrap_refactor_state", BOOTSTRAP_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BOOTSTRAP = load_bootstrap_module()
REFACTOR_DIR = BOOTSTRAP.BASE_PATH
MODULES_DIR = BOOTSTRAP.MODULES_PATH
CONTROL_FILE_NAMES = set(BOOTSTRAP.INITIAL_FILES) | {"refactor_state.json"}
REQUIRED_CONTROL_PATHS = [REFACTOR_DIR / relative_path for relative_path in BOOTSTRAP.INITIAL_FILES] + [
    REFACTOR_DIR / "refactor_state.json"
]
ALLOWED_STATES = set(BOOTSTRAP.ALLOWED_MODULE_STATES)
EXPECTED_QUEUE_CODES = [code for code, _name in BOOTSTRAP.MODULE_QUEUE]


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
