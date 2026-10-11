"""Read-only historical StandardDialog reproduction for phase 9 regression audit."""
from __future__ import annotations

import hashlib
import importlib.abc
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
NAME = "frontend.desktop.components.dialogs"
REVISION = "29317dca^"
SOURCE_PATH = "pos_spj_v13.4/frontend/desktop/components/dialogs.py"
SOURCE = subprocess.check_output(["git", "show", f"{REVISION}:{SOURCE_PATH}"], cwd=ROOT)


class HistoricalDialogLoader(importlib.abc.Loader):
    def create_module(self, spec):
        return None

    def exec_module(self, module):
        module.__file__ = f"git:{REVISION}:{SOURCE_PATH}"
        exec(compile(SOURCE, module.__file__, "exec"), module.__dict__)
        module.__baseline_sha256__ = hashlib.sha256(SOURCE).hexdigest()


class HistoricalDialogFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == NAME:
            return importlib.util.spec_from_loader(fullname, HistoricalDialogLoader())
        return None


assert NAME not in sys.modules, "Historical override must precede component imports"
sys.meta_path.insert(0, HistoricalDialogFinder())


def pytest_sessionfinish(session, exitstatus):
    module = sys.modules.get(NAME)
    details = {
        "revision": subprocess.check_output(["git", "rev-parse", REVISION], cwd=ROOT, text=True).strip(),
        "source_path": SOURCE_PATH,
        "source_sha256": hashlib.sha256(SOURCE).hexdigest(),
        "loaded_file": getattr(module, "__file__", None),
        "loaded_sha256": getattr(module, "__baseline_sha256__", None),
        "has_new_heading_method": hasattr(module.StandardDialog, "_update_heading") if module else None,
        "exitstatus": int(exitstatus),
    }
    Path(__file__).with_name("dialog-baseline-proof.json").write_text(
        json.dumps(details, indent=2), encoding="utf-8"
    )
