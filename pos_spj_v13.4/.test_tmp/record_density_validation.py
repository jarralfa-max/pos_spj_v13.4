"""Archive density checks and captures without replacing earlier phase evidence."""
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

out = root / "docs/refactor/evidence/density_profiles_phase_7"
out.mkdir(parents=True, exist_ok=True)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
before = json.loads((root / ".test_tmp/density-phase7-before.json").read_text(encoding="utf-8"))
cases, results = {}, []
for name in sys.argv[1:]:
    path = root / ".test_tmp" / f"{name}.xml"
    counts = Counter(passed=0, failed=0, errors=0, skipped=0)
    for case in ET.parse(path).iter("testcase"):
        status = "failed" if case.find("failure") is not None else "errors" if case.find("error") is not None else "skipped" if case.find("skipped") is not None else "passed"
        key = (case.get("classname"), case.get("name"))
        if key in cases:
            assert cases[key] == status, f"Inconsistent duplicate result: {key}"
        cases[key] = status
        counts[status] += 1
    results.append(dict(name=name, **counts))
    shutil.copy2(path, out / path.name)
    raw = path.with_suffix(".log").read_bytes()
    text = raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig", errors="replace")
    (out / path.with_suffix(".log").name).write_text(text, encoding="utf-8")

findings = scan_repository()
new, obsolete = regressions(findings, json.loads(BASELINE.read_text(encoding="utf-8")))
after = dict(files=sum(1 for _ in sources()), rules=summarize(findings),
             unallowlisted=[dict(key=list(key), count=count) for key, count in sorted(new.items())],
             obsolete=sum(obsolete.values()))
assert after["unallowlisted"] == before["unallowlisted"], "Reassess visual debt before closing"
images = [{"file": p.name, "sha256": sha(p)} for p in sorted(out.glob("*.png"))]
extra = ["frontend/desktop/components/virtual_keyboard.py",
         "tests/ui/test_keyboard_density_target.py",
         "frontend/desktop/modules/configuracion/pages/apariencia_page.py"]
paths = list(before["source_sha256"]) + extra + [p.relative_to(root).as_posix() for p in (root / "tests/ui").glob("test_density*.py")] + ["tests/ui/test_terminal_density_selector.py"]
payload = dict(phase="7. Density profiles", date="2026-09-23", results=results,
               distinct_totals=dict(Counter(cases.values())), baseline_before=before,
               audit_after=after, new_visual_violations_since_start=0,
               source_sha256={name: sha(root / name) for name in paths}, captures=images,
               scope="Qt offscreen with Windows fonts and isolated settings; no hardware or production database run")
(out / "validation.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
for name in ("density-existing-before", "density-round-trip-before", "density-selector-before",
             "density-sidebar-before", "density-targets-before", "density-focus-popup-before",
             "density-focused-before", "keyboard-density-before"):
    shutil.copy2(root / ".test_tmp" / f"{name}.xml", out / f"{name}.xml")

cards = "\n".join(f'<figure data-name="{html.escape(item["file"])}"><a href="{html.escape(item["file"])}"><img loading="lazy" src="{html.escape(item["file"])}" alt="{html.escape(item["file"])}"></a><figcaption>{html.escape(item["file"])}</figcaption></figure>' for item in images)
page = '''<!doctype html><html lang="es"><meta charset="utf-8"><title>JUANIS · Perfiles de densidad</title>
<style>body{font:16px system-ui;margin:24px;background:#f5f5f5;color:#252825}header{position:sticky;top:0;background:#f5f5f5;padding:12px 0}input{font:inherit;padding:8px;width:min(90%,520px)}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:20px}figure{margin:0;background:white;padding:10px}img{width:100%;height:auto}figcaption{font-size:13px;overflow-wrap:anywhere}[hidden]{display:none}</style>
<header><h1>Perfiles de densidad</h1><p>Capturas Qt de Claro/Oscuro y Compacta/Cómoda/Táctil. Revisión automática de geometría; no comparación con una referencia de píxeles aprobada.</p><p><a href="validation.json">Resultados y hashes</a> · <a href="../../density_profiles_phase_7.md">Informe</a></p><label>Filtrar capturas <input id="filter" type="search" placeholder="touch, dark, 1280x720…"></label></header><main>''' + cards + '''</main><script>document.getElementById('filter').addEventListener('input',event=>{const q=event.target.value.toLowerCase();document.querySelectorAll('figure').forEach(f=>f.hidden=!f.dataset.name.includes(q));});</script></html>'''
(out / "index.html").write_text(page, encoding="utf-8")
print(json.dumps(dict(totals=payload["distinct_totals"], captures=len(images), audit=after), ensure_ascii=True))
