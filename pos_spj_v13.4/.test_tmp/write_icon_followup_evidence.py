"""Record the focused IconProvider follow-up without replacing phase evidence."""
import hashlib
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from tests.architecture.design_system_audit import BASELINE, regressions, scan_repository, summarize

evidence = root / "docs/refactor/evidence/icon_provider_phase_5"
runs = []
for name in ("icon-provider-followup-before", "icon-provider-followup"):
    source = root / ".test_tmp" / f"{name}.xml"
    suites = ET.parse(source).getroot()
    cases = list(suites.iter("testcase"))
    failures = sum(case.find("failure") is not None for case in cases)
    errors = sum(case.find("error") is not None for case in cases)
    skipped = sum(case.find("skipped") is not None for case in cases)
    runs.append({
        "name": name, "tests": len(cases), "passed": len(cases) - failures - errors - skipped,
        "failures": failures, "errors": errors, "skipped": skipped,
        "cases": [{"name": f"{case.get('classname')}::{case.get('name')}",
                   "result": "failed" if case.find("failure") is not None else
                             "error" if case.find("error") is not None else
                             "skipped" if case.find("skipped") is not None else "passed"}
                  for case in cases],
    })
    shutil.copyfile(source, evidence / source.name)
    log = source.with_suffix(".log")
    shutil.copyfile(log, evidence / log.name)

findings = scan_repository()
new, obsolete = regressions(findings, json.loads(BASELINE.read_text(encoding="utf-8")))
paths = ["frontend/desktop/components/icons.py", "tests/ui/test_icon_provider_runtime.py",
         "frontend/desktop/design_system/migration_guide.md"]
payload = {
    "phase": "5. IconProvider — follow-up", "date": "2026-09-13", "runs": runs,
    "new_test_cases": 6,
    "audit": {"existing_occurrences": len(findings), "new_violations": sum(new.values()),
              "obsolete_fingerprints": sum(obsolete.values()), "rules": summarize(findings)},
    "source_sha256": {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths},
    "visual_evidence": {"reused_historical_manifest": "validation.json", "new_captures": 0,
                        "reason": "Binding lifecycle and accessibility changes; artwork unchanged."},
    "limits": ["Focused affected segments, not a global test run.",
               "DPR screen changes simulated with real Qt offscreen; physical monitors pending."],
}
(evidence / "followup-validation.json").write_text(
    json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"runs": [{k: v for k, v in run.items() if k != "cases"} for run in runs],
                  "audit": payload["audit"]}, indent=2))
