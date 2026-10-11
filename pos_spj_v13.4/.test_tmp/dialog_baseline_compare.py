"""Summarize unrelated failures with historical StandardDialog in memory."""
from pathlib import Path
import ast
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET

TMP = Path(__file__).resolve().parent
INNER = TMP.parent
OUTER = INNER.parent
REV = "29317dca^"


def failed(path):
    result = {}
    for case in ET.parse(path).iter("testcase"):
        failure = case.find("failure")
        if failure is not None:
            nodeid = case.attrib["classname"].replace(".", "/") + ".py::" + case.attrib["name"]
            result[nodeid] = re.sub(r"0x[0-9A-Fa-f]+", "0xADDRESS", failure.attrib["message"])
    return result


before = failed(TMP / "dialog-baseline-six.xml")
after = failed(TMP / "standard-dialog-regression.xml")
comparison = {key: before[key] == after.get(key) for key in before}
paths = [
    "frontend/desktop/modules/sales_pos/dialogs/payment_dialog.py",
    "frontend/desktop/components/search_selector.py",
    "frontend/desktop/components/status_badge.py",
    "tests/unit/test_pos_checkout_dialogs.py",
    "tests/unit/test_phase3_ui_components.py",
]
unchanged = {}
for relative in paths:
    historical = subprocess.check_output(["git", "show", f"{REV}:pos_spj_v13.4/{relative}"], cwd=OUTER)
    current = (INNER / relative).read_bytes().replace(b"\r\n", b"\n")
    unchanged[relative] = historical.replace(b"\r\n", b"\n") == current

workspace = "frontend/desktop/modules/sales_pos/sales_pos_workspace.py"
old = subprocess.check_output(["git", "show", f"{REV}:pos_spj_v13.4/{workspace}"], cwd=OUTER).decode("utf-8")
new = (INNER / workspace).read_text(encoding="utf-8")


def methods(source):
    return {node.name: ast.dump(node, include_attributes=False)
            for node in ast.walk(ast.parse(source)) if isinstance(node, ast.FunctionDef)}


old_methods, new_methods = methods(old), methods(new)
report = {
    "historical_dialog": json.loads((TMP / "dialog-baseline-proof.json").read_text()),
    "scope": "Only StandardDialog module is historical; current test/environment/dependencies preserved.",
    "memory_addresses_normalized": True,
    "same_failure": comparison,
    "all_six_failures_reproduced": len(comparison) == 6 and all(comparison.values()),
    "unchanged_against_pre_phase9_commit": unchanged,
    "sales_pos_methods_unchanged": {name: old_methods[name] == new_methods[name]
                                    for name in ("_has_lines", "_on_checkout_requested", "_warn")},
    "deleted_legacy_file": {
        "path": "modulos/merma.py",
        "current_exists": (INNER / "modulos/merma.py").exists(),
        "historical_exists": subprocess.run(["git", "cat-file", "-e", f"{REV}:pos_spj_v13.4/modulos/merma.py"], cwd=OUTER, capture_output=True).returncode == 0,
    },
}
(TMP / "dialog-baseline-comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
