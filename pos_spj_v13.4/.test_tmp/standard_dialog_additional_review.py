"""Read-only attribution of the additional phase 9 architecture failures."""
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

TMP = Path(__file__).resolve().parent
INNER = TMP.parent
OUTER = INNER.parent
sys.path.insert(0, str(INNER))
from tests.architecture.design_system_audit import scan_source


def git(*args):
    return subprocess.check_output(["git", *args], cwd=OUTER)


HEAD = git("rev-parse", "HEAD").decode().strip()
BEFORE_COMMIT = git("rev-parse", "29317dca").decode().strip()
PRE_PHASE9 = git("rev-parse", "29317dca^").decode().strip()


def historical(revision, path):
    process = subprocess.run(["git", "show", f"{revision}:pos_spj_v13.4/{path}"], cwd=OUTER, capture_output=True)
    return process.stdout.decode("utf-8-sig") if process.returncode == 0 else None


def normalized(text):
    return text.replace("\r\n", "\n")


def digest(text):
    return hashlib.sha256(normalized(text).encode("utf-8")).hexdigest() if text is not None else None


def key(finding):
    return finding["path"], finding["rule"], finding["fingerprint"]


runs = {}
failures = []
for name in ("standard-dialog-contracts.xml", "standard-dialog-finance-hr-architecture.xml"):
    cases = list(ET.parse(TMP / name).iter("testcase"))
    counts = Counter()
    for case in cases:
        state = ("FAILED" if case.find("failure") is not None else "ERROR" if case.find("error") is not None
                 else "SKIPPED" if case.find("skipped") is not None else "PASSED")
        counts[state] += 1
        if state == "FAILED":
            failures.append({
                "run": name,
                "nodeid": case.attrib["classname"].replace(".", "/") + ".py::" + case.attrib["name"],
                "message": case.find("failure").attrib["message"],
            })
    runs[name] = {s: counts[s] for s in ("PASSED", "FAILED", "SKIPPED", "ERROR")}

before_path = TMP / "standard-dialog-audit-before.json"
before_audit = json.loads(before_path.read_text(encoding="utf-8-sig"))
before_keys = {key(f) for f in before_audit["findings"]}
debt_message = next(f["message"] for f in failures if f["nodeid"].endswith("::test_desktop_visual_debt_does_not_grow"))
violations = re.findall(r"^\s*(frontend/[^:]+):(\d+): (\w+): (.+)$", debt_message, flags=re.M)
attributions = []
for path, line, rule, expression in violations:
    current = (INNER / path).read_text(encoding="utf-8-sig")
    head_source = historical(HEAD, path)
    parent_source = historical(BEFORE_COMMIT, path)
    item = next(f for f in scan_source(current, path) if f.rule == rule and f.expression == expression)
    head_keys = {f.key for f in scan_source(head_source, path)} if head_source else set()
    parent_keys = {f.key for f in scan_source(parent_source, path)} if parent_source else set()
    attributions.append({
        **asdict(item),
        "present_in_before_audit": item.key in before_keys,
        "present_in_29317dca_ast": item.key in parent_keys,
        "present_in_head_ast": item.key in head_keys,
        "source_matches_head": digest(current) == digest(head_source),
        "current_source_sha256": digest(current),
        "head_source_sha256": digest(head_source),
        "classification": ("preexisting_before_audit" if item.key in before_keys else "concurrent_crm_commit"),
    })

missing_paths = ("modulos/configuracion.py", "modulos/rrhh.py", "frontend/desktop/modules/customers_crm/pages/_directory_base.py")
missing = []
for path in missing_paths:
    deletion = git("log", "-1", "--format=%H %s", "--diff-filter=D", "--", f"pos_spj_v13.4/{path}").decode().strip()
    missing.append({
        "path": path,
        "currently_exists": (INNER / path).is_file(),
        "exists_at_pre_phase9": historical(PRE_PHASE9, path) is not None,
        "exists_at_29317dca": historical(BEFORE_COMMIT, path) is not None,
        "exists_at_head": historical(HEAD, path) is not None,
        "deletion_commit": deletion,
    })

tests = {}
for path in ("tests/architecture/test_settings_dialog_buttons_spanish.py", "tests/architecture/test_hr_architecture.py",
             "tests/architecture/test_design_system_guardrails.py", "tests/architecture/design_system_audit.py"):
    current = (INNER / path).read_text(encoding="utf-8-sig")
    tests[path] = {
        "sha256": digest(current),
        "matches_head": digest(current) == digest(historical(HEAD, path)),
        "matches_pre_phase9": digest(current) == digest(historical(PRE_PHASE9, path)),
    }

baseline_path = "tests/architecture/design_system_debt_baseline.json"
head_baseline = json.loads(historical(HEAD, baseline_path))
stale_path = "frontend/desktop/modules/customers_crm/pages/_directory_base.py"
report = {
    "scope": "Read-only attribution; no production or existing test files modified.",
    "head_at_review": HEAD,
    "before_commit": BEFORE_COMMIT,
    "pre_phase9_commit": PRE_PHASE9,
    "runs": runs,
    "totals": {s: sum(r[s] for r in runs.values()) for s in ("PASSED", "FAILED", "SKIPPED", "ERROR")},
    "failures": failures,
    "before_audit_path": str(before_path.relative_to(INNER)).replace("\\", "/"),
    "before_audit_sha256": hashlib.sha256(before_path.read_bytes()).hexdigest(),
    "visual_violation_counts": {
        "total": len(attributions),
        "present_in_before_audit": sum(a["present_in_before_audit"] for a in attributions),
        "new_crm_concurrent_commit": sum(a["classification"] == "concurrent_crm_commit" for a in attributions),
        "all_already_committed_at_head": all(a["present_in_head_ast"] and a["source_matches_head"] for a in attributions),
    },
    "visual_violations": attributions,
    "missing_files": missing,
    "stale_crm_baseline_entries_committed_at_head": [f for f in head_baseline["findings"] if f["path"] == stale_path],
    "test_and_scanner_sources": tests,
    "conclusion": "The global audit grew by nine CRM overflow findings from concurrent commit d9f2bcaf, which also deleted an allowlisted CRM file. Four findings already existed before the phase. Configuration/HR tests reference older deleted legacy files. None of these failures is caused by the StandardDialog edits; the global guardrails still fail and are not claimed clean.",
}
output = TMP / "standard-dialog-additional-failures.json"
output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps({"output": str(output), "runs": runs, "totals": report["totals"], "visual_violation_counts": report["visual_violation_counts"], "missing_files": missing}, indent=2))
