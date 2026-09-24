"""Record StandardWindow checks separately from preceding density evidence."""
from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from tests.architecture.design_system_audit import BASELINE, regressions, scan_repository, sources, summarize

out = root / "docs/refactor/evidence/standard_window_phase_8"
out.mkdir(parents=True, exist_ok=True)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
cases, results = {}, []
for name in sys.argv[1:]:
    path = root / ".test_tmp" / f"{name}.xml"
    counts = Counter(passed=0, failed=0, errors=0, skipped=0)
    for case in ET.parse(path).iter("testcase"):
        status = "failed" if case.find("failure") is not None else "errors" if case.find("error") is not None else "skipped" if case.find("skipped") is not None else "passed"
        cases[(case.get("classname"), case.get("name"))] = status
        counts[status] += 1
    results.append(dict(name=name, **counts))
    shutil.copy2(path, out / path.name)
    raw = path.with_suffix(".log").read_bytes()
    text = raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig", errors="replace")
    (out / path.with_suffix(".log").name).write_text(text, encoding="utf-8")
findings = scan_repository()
new, obsolete = regressions(findings, json.loads(BASELINE.read_text(encoding="utf-8")))
audit = dict(files=sum(1 for _ in sources()), rules=summarize(findings),
             unallowlisted=[dict(key=list(key), count=count) for key, count in sorted(new.items())], obsolete=sum(obsolete.values()))
before = json.loads((root / "docs/refactor/evidence/density_profiles_phase_7/validation.json").read_text(encoding="utf-8"))["audit_after"]
assert audit == before
images = [{"file": p.name, "sha256": sha(p)} for p in sorted(out.glob("*.png"))]
paths = ["frontend/desktop/components/standard_window.py", "frontend/desktop/design_system/component_contracts.py",
         "frontend/desktop/shell/application_shell/status_bar.py", "tests/ui/shell/test_status_bar.py",
         "tests/ui/test_design_system_visual_matrix.py", "tests/ui/test_design_system_navigation_visuals.py",
         "tests/ui/test_density_profiles_visuals.py",
         "tests/ui/test_appearance_theme_visuals.py",
         "tests/ui/test_standard_window_geometry.py", "tests/ui/test_standard_window_visuals.py",
         "tests/architecture/test_standard_window_ownership.py"]
payload = dict(phase="8. StandardWindow", date="2026-09-23", results=results,
               distinct_totals={s: list(cases.values()).count(s) for s in ("passed", "failed", "errors", "skipped")},
               audit_before=before, audit_after=audit, new_visual_violations=0,
               source_sha256={name: sha(root / name) for name in paths}, captures=images,
               scope="Qt offscreen; physical multi-monitor and Windows DPI not certified",
               available_area_sizes=[[1280,720],[1366,768],[1440,900],[1600,900],[1920,1080]])
shutil.copy2(root / ".test_tmp/window-phase8-before.xml", out / "window-phase8-before.xml")
shutil.copy2(root / ".test_tmp/window-status-before.xml", out / "window-status-before.xml")
(out / "validation.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
cards = "\n".join(f'<figure><a href="{html.escape(i["file"])}"><img loading="lazy" src="{html.escape(i["file"])}" alt="{html.escape(i["file"])}"></a><figcaption>{html.escape(i["file"])}</figcaption></figure>' for i in images)
(out / "index.html").write_text('''<!doctype html><html lang="es"><meta charset="utf-8"><title>StandardWindow · JUANIS</title><style>body{font:16px system-ui;margin:24px;background:#f5f5f5}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(350px,1fr));gap:20px}figure{margin:0;background:white;padding:10px}img{width:100%;height:auto}figcaption{font-size:13px;overflow-wrap:anywhere}</style><h1>StandardWindow</h1><p>Claro/Oscuro · Compacta/Cómoda/Táctil · Cinco áreas de escritorio simuladas. Las capturas muestran el contenido; las pruebas comprueban también el marco nativo.</p><p><a href="validation.json">Resultados y hashes</a> · <a href="../../standard_window_phase_8.md">Informe</a></p><main>''' + cards + '</main></html>', encoding="utf-8")
print(json.dumps(dict(totals=payload["distinct_totals"], captures=len(images))))
