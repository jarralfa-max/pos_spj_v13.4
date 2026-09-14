"""Collect this correction's evidence without overwriting earlier phase reports."""
import hashlib
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from tests.architecture.design_system_audit import BASELINE, regressions, scan_repository, summarize

evidence = root / "docs/refactor/evidence/module_sidebar_icons"
evidence.mkdir(parents=True, exist_ok=True)
names = [
    "module-sidebar-final-regression", "sidebar-finance-hr-purchasing-integration",
    "sidebar-purchasing", "operational-sidebar-icons-reviewed",
    "operational-sidebar-regression-reviewed", "route-sidebar-icons",
    *sys.argv[1:],
]
before_names = ["sidebar-finance-hr-before", "sidebar-purchasing-before",
                "operational-sidebar-before", "route-sidebar-icons-before", "sidebar-icon-guardrail"]


def record(name):
    source = root / ".test_tmp" / f"{name}.xml"
    cases = []
    for case in ET.parse(source).getroot().iter("testcase"):
        outcome = next((tag for tag in ("failure", "error", "skipped") if case.find(tag) is not None), "passed")
        cases.append({"name": f"{case.get('classname')}::{case.get('name')}", "outcome": outcome})
    for extension in ("xml", "log"):
        source_file = source.with_suffix(f".{extension}")
        shutil.copyfile(source_file, evidence / source_file.name)
    return {"name": name, "tests": len(cases),
            **{key: sum(case["outcome"] == key for case in cases)
               for key in ("passed", "failure", "error", "skipped")}, "cases": cases}


runs = [record(name) for name in names]
before = [record(name) for name in before_names]
unique = {}
for run in runs:
    for case in run["cases"]:
        previous = unique.setdefault(case["name"], case["outcome"])
        assert previous == case["outcome"], f"Conflicting outcomes for {case['name']}"
totals = {key: sum(outcome == key for outcome in unique.values())
          for key in ("passed", "failure", "error", "skipped")}
findings = scan_repository()
new, obsolete = regressions(findings, json.loads(BASELINE.read_text(encoding="utf-8")))
source_names = [
    "frontend/desktop/modules/finance/finance_view.py", "frontend/desktop/modules/hr/hr_view.py",
    "frontend/desktop/modules/purchasing/navigation.py", "frontend/desktop/modules/purchasing/purchasing_module_shell.py",
    "frontend/desktop/modules/products/products_view.py", "frontend/desktop/modules/products/composition.py",
    "frontend/desktop/modules/inventory/inventory_view.py", "frontend/desktop/modules/pricing/pricing_workspace.py",
    *[f"frontend/desktop/modules/{name}/widgets/{name}_sidebar_widget.py" for name in (
        "losses", "meat_processing", "orders_delivery", "business_intelligence", "transfers", "configuracion")],
    *[f"frontend/desktop/modules/{name}/{name}_{kind}.py" for name in (
        "cash_register", "customers_crm", "fidelidad", "tarjetas_fidelidad", "assets") for kind in ("routes", "workspace")],
    "tests/architecture/test_icon_catalog.py", "tests/integration/suppliers/test_supplier_ui.py",
    *[f"tests/ui/test_{name}.py" for name in ("finance_hr_sidebar_icons", "purchasing_sidebar_icons",
        "operational_sidebar_icons", "route_sidebar_icons", "module_sidebar_icon_visuals")],
]
payload = {
    "correction": "Module sidebars must display their route icons", "date": "2026-09-14",
    "affected_modules": 17, "unique_results": totals, "runs": runs, "before_runs": before,
    "audit": {"new_violations": sum(new.values()), "obsolete_fingerprints": sum(obsolete.values()),
              "existing_occurrences": len(findings), "rules": summarize(findings)},
    "source_sha256": {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in source_names},
    "visual_artifacts": [{"path": path.relative_to(evidence).as_posix(),
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                         for path in sorted(evidence.rglob("*.png"))],
    "known_prior_failure": "test_legacy_produccion_menu_entry_and_module_are_not_touched_yet reads interfaz/menu_lateral.py, absent in the working tree and HEAD.",
    "limits": ["Affected segments, not the full project suite.",
               "Screenshots show real module navigation with neutral page bodies and no business database.",
               "Focused navigation at 768px height; not the full application resolution matrix or physical monitor acceptance."],
}
(evidence / "validation.json").write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"unique_results": totals, "png_count": len(payload["visual_artifacts"]),
                  "audit": payload["audit"],
                  "runs": [{k: v for k, v in run.items() if k != "cases"} for run in runs]}, indent=2))
