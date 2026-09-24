"""Record this phase's actual Qt captures and JUnit results."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.architecture.design_system_audit import BASELINE, regressions, scan_repository, sources, summarize

out = ROOT / "docs/refactor/evidence/qss_global_phase_4"
out.mkdir(parents=True, exist_ok=True)
names = ["qss-runtime-regression", "qss-global-contracts", "qss-ownership", "qss-global-visuals", "qss-states-visuals"]
if (ROOT / ".test_tmp/qss-spin.xml").exists():
    names.append("qss-spin")
results, cases = [], {}
for name in names:
    path = ROOT / ".test_tmp" / f"{name}.xml"
    tree = ET.parse(path)
    counts = dict(passed=0, failed=0, errors=0, skipped=0)
    for case in tree.iter("testcase"):
        status = "failed" if case.find("failure") is not None else "errors" if case.find("error") is not None else "skipped" if case.find("skipped") is not None else "passed"
        counts[status] += 1
        cases[(case.get("classname"), case.get("name"))] = status
    results.append(dict(name=name, **counts))
    shutil.copy2(path, out / path.name)
    log = path.with_suffix(".log")
    if log.exists():
        raw = log.read_bytes()
        text = raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
        (out / log.name).write_text(text, encoding="utf-8")
for name in ("qss-runtime-before", "qss-existing-before", "qss-spin-before"):
    path = ROOT / ".test_tmp" / f"{name}.xml"
    if path.exists():
        shutil.copy2(path, out / path.name)
findings = scan_repository()
new, resolved = regressions(findings, json.loads(BASELINE.read_text(encoding="utf-8")))
assert dict(new) == {
    ("frontend/desktop/modules/pricing/pages/settings_page.py", "screen_without_explicit_overflow", "eecdb14c0a9c4a98cf33"): 1,
    ("frontend/desktop/modules/meat_processing/pages/meat_processing_settings_page.py", "screen_without_explicit_overflow", "ccda8fcb6a5694ec8cac"): 1,
}, "Reassess audit delta before reporting"
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
payload = {
    "phase": "4. QSS global", "date": "2026-09-21",
    "scope": "Global native Qt appearance; no business operations or database changes",
    "results": results,
    "distinct_totals": {status: list(cases.values()).count(status) for status in ("passed", "failed", "errors", "skipped")},
    "visual_baseline": "Qt captures and semantic pixel/geometry assertions; no approved golden images",
    "audit": {"files_scanned": len(list(sources())), "rules": summarize(findings),
        "allowlisted_occurrences": sum(item["count"] for item in json.loads(BASELINE.read_text(encoding="utf-8"))["findings"]),
        "unallowlisted_occurrences": sum(new.values()), "obsolete_occurrences": sum(resolved.values()),
        "unallowlisted_outside_phase": [{"path": key[0], "rule": key[1], "fingerprint": key[2], "count": count} for key, count in new.items()],
        "baseline_sha256": sha(BASELINE), "introduced_by_this_phase": 0},
    "source_sha256": {name: sha(ROOT / name) for name in (
        "frontend/desktop/themes/qss_builder.py", "frontend/desktop/themes/theme_manager.py",
        "tests/ui/test_global_qss_runtime.py", "tests/ui/test_global_qss_visuals.py",
        "tests/ui/test_spin_controls_rendering.py", "tests/architecture/test_global_qss_ownership.py")},
    "captures": [{"file": p.name, "sha256": sha(p)} for p in sorted(out.glob("*.png"))],
}
(out / "validation.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
viewer = (ROOT / "docs/refactor/evidence/light_dark_phase_3/index.html").read_text(encoding="utf-8")
viewer = viewer.replace("12 septiembre 2026", "21 septiembre 2026").replace("Evidencia visual del Design System", "QSS global: componentes y estados")
viewer = viewer.replace("Los recursos oficiales de marca siguen pendientes.", "Incluye los recursos de JUANIS entregados el 21 de septiembre.")
viewer = viewer.replace('<option value="appearance">Apariencia: selector de tema de terminal</option>', '<option value="qss-states">Tarjetas, campos y acciones</option>')
viewer = viewer.replace("const name=fields.map(field=>field.value).join('-')+'.png';", "const [theme,density,size,scene]=fields.map(field=>field.value);\n const name=(scene==='qss-states' ? `qss-states-${theme}-${density}-${size}` : `${theme}-${density}-${size}-${scene}`)+'.png';")
viewer = viewer.replace("<form>", '<p><a href="../../qss_global_phase_4.md">Informe</a> · <a href="validation.json">Pruebas y hashes</a></p>\n<form>')
(out / "index.html").write_text(viewer, encoding="utf-8")
print(json.dumps({"totals": payload["distinct_totals"], "captures": len(payload["captures"]), "audit": payload["audit"]}, ensure_ascii=True))
