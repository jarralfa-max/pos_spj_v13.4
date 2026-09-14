"""Build the reviewable evidence manifest from actual pytest and Qt outputs."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from frontend.desktop.themes.color_utils import contrast_ratio
from frontend.desktop.themes.semantic_colors import Light, Dark
from tests.architecture.design_system_audit import scan_repository, regressions, summarize

root = Path.cwd()
artifacts = root / "docs/refactor/evidence/light_dark_phase_3"
run_names = [
    "light-dark-runtime", "light-dark-contrast", "light-dark-guardrails-integration",
    "light-dark-visuals", "light-dark-combo",
]
runs = []
unique = set()
for name in run_names:
    report = ET.parse(root / ".test_tmp" / (name + ".xml")).getroot()
    suites = report.findall("testsuite")
    cases = report.findall(".//testcase")
    summary = {key: sum(int(s.get(key, 0)) for s in suites)
               for key in ("tests", "failures", "errors", "skipped")}
    assert summary["failures"] == summary["errors"] == summary["skipped"] == 0, (name, summary)
    case_names = sorted(c.get("classname", "") + "::" + c.get("name", "") for c in cases)
    unique.update(case_names)
    runs.append({"name": name, **summary, "cases": case_names,
                 "source": f".test_tmp/{name}.xml"})

screenshots = [{"name": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
               for p in sorted(artifacts.glob("*.png"))]
assert len(screenshots) == 220, len(screenshots)
baseline = json.loads((root / "tests/architecture/design_system_debt_baseline.json").read_text(encoding="utf-8"))
findings = scan_repository()
new, stale = regressions(findings, baseline)
audit = {"new_violations": sum(new.values()), "stale_baseline_entries": sum(stale.values()),
         "existing_occurrences": len(findings), "rules": summarize(findings)}
assert not new and not stale, audit
ratios = {name: {
    "helper_on_background": contrast_ratio(theme.TEXT_MUTED, theme.BACKGROUND),
    "helper_on_surface": contrast_ratio(theme.TEXT_MUTED, theme.SURFACE),
    "input_border_on_surface": contrast_ratio(theme.INPUT_BORDER, theme.SURFACE),
    "input_border_on_background": contrast_ratio(theme.INPUT_BORDER, theme.BACKGROUND),
} for name, theme in (("light", Light), ("dark", Dark))}
ratios["light"]["focus_on_primary"] = contrast_ratio(Light.FOCUS_RING, Light.PRIMARY_DEFAULT)
result = {
    "phase": "3. Light / Dark", "date": "2026-09-12",
    "passed_unique": len(unique), "runs": runs, "audit": audit,
    "measured_contrast": ratios, "screenshots": screenshots,
    "limitations": [
        "Targeted suites only; previous complete-suite failures remain documented in the global audit.",
        "Screenshots use real Qt widgets and example data, without an approved pixel baseline.",
        "QtWebEngine/ECharts rendering unavailable; HTML refresh is covered through an HTML receiver.",
        "Real terminal DPI, touch hardware and official brand assets require acceptance.",
    ],
}
(artifacts / "validation.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({"passed_unique": len(unique), "runs": [{k:v for k,v in r.items() if k != "cases"} for r in runs],
                  "audit": audit, "screenshots": len(screenshots), "contrast": ratios}, ensure_ascii=False))
