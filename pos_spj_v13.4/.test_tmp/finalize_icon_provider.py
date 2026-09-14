import ast
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from frontend.desktop.components.icons import all_icons, _PATHS, icon_accessible_name
from tests.architecture.design_system_audit import scan_repository, regressions, summarize

root = Path.cwd()
output = root / 'docs/refactor/evidence/icon_provider_phase_5'
run_names = ('icon-provider-runtime', 'icon-provider-visuals',
             'icon-provider-regression', 'icon-provider-catalog-label', 'icon-provider-catalog-guard')
runs, unique = [], set()
for name in run_names:
    xml = ET.parse(root / '.test_tmp' / f'{name}.xml').getroot()
    summary = {key: sum(int(s.get(key, 0)) for s in xml.findall('testsuite'))
               for key in ('tests', 'failures', 'errors', 'skipped')}
    assert not any(summary[key] for key in ('failures', 'errors', 'skipped')), (name, summary)
    cases = sorted(c.get('classname', '') + '::' + c.get('name', '') for c in xml.findall('.//testcase'))
    unique.update(cases)
    runs.append({'name': name, **summary, 'cases': cases})
baseline = json.loads((root / 'tests/architecture/design_system_debt_baseline.json').read_text(encoding='utf-8'))
findings = scan_repository()
new, stale = regressions(findings, baseline)
assert not new and not stale
icons = [{'identifier': name, 'accessible_name': icon_accessible_name(name)} for name in all_icons()]
pngs = [{'name': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in sorted(output.glob('*.png'))]
assert len(pngs) == 210
nav_count = 0
for path in (root / 'frontend/desktop').rglob('*.py'):
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    classes = {node.name for node in tree.body if isinstance(node, ast.ClassDef) and node.name.endswith('NavEntry')}
    nav_count += sum(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                     and node.func.id in classes for node in ast.walk(tree))
result = {
    'phase': '5. IconProvider', 'date': '2026-09-13',
    'passed_unique': len(unique), 'runs': runs, 'icons': icons,
    'identifiers': len(icons), 'unique_vectors': len(set(_PATHS.values())),
    'navigation_declarations': nav_count,
    'audit': {'new_violations': sum(new.values()), 'stale_baseline_entries': sum(stale.values()),
              'existing_occurrences': len(findings), 'rules': summarize(findings)},
    'screenshots': pngs,
    'limitations': [
        'Targeted test segments; previous full-suite failures remain in the global audit.',
        'Fourteen preexisting Unicode findings remain for module adoption; not all are actionable icons.',
        'Offscreen Qt geometry and state checks do not replace hardware/DPI acceptance or an approved pixel baseline.',
        'Interface artwork is separate from the missing official JUANIS logo assets.',
    ],
}
(output / 'validation.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
html = '''<!doctype html>
<html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>JUANIS · IconProvider</title>
<style>body{font:16px system-ui,sans-serif;margin:24px;background:#f8f8f5;color:#252825}h1{font-size:24px}
form{display:flex;gap:20px;flex-wrap:wrap;margin:24px 0}label{display:grid;gap:6px}select{font:inherit;padding:10px}
img{display:block;max-width:100%;height:auto}p{max-width:900px;line-height:1.5}a{color:#18372b}figure{margin:0}</style>
<h1>JUANIS · Catálogo IconProvider</h1>
<p>138 identificadores semánticos y 99 vectores. Diez láminas Qt muestran todos los símbolos en
Claro/Oscuro y ocho estados. La deshabilitación también se aplica al control nativo.</p>
<p><a href="shell.html">Ver las 200 capturas de shell, navegación y componentes</a> ·
<a href="validation.json">Resultados y hashes</a></p>
<p>Validación automatizada con datos de ejemplo. Revisión de hardware y referencias visuales aprobadas pendiente.</p>
<form><label>Tema<select id="theme"><option value="light">Claro</option><option value="dark">Oscuro</option></select></label>
<label>Lámina<select id="page"><option>1</option><option>2</option><option>3</option><option>4</option><option>5</option></select></label></form>
<figure><figcaption><a id="original">Abrir original</a></figcaption><img id="capture" alt="Catálogo de iconos JUANIS"></figure>
<script>const theme=document.getElementById('theme'),page=document.getElementById('page');
function update(){const name='catalog-'+theme.value+'-'+page.value+'.png';document.getElementById('capture').src=name;
document.getElementById('original').href=name;document.getElementById('capture').alt='IconProvider · '+theme.selectedOptions[0].text+' · Lámina '+page.value;}
theme.addEventListener('change',update);page.addEventListener('change',update);update();</script></html>
'''
(output / 'index.html').write_text(html, encoding='utf-8')
shell = (root / 'docs/refactor/evidence/design_system_ui/index.html').read_text(encoding='utf-8')
shell = shell.replace('12 septiembre 2026', '13 septiembre 2026')
shell = shell.replace('JUANIS · Evidencia visual del Design System', 'JUANIS · IconProvider en el shell')
(output / 'shell.html').write_text(shell, encoding='utf-8')
print(json.dumps({k: v for k, v in result.items() if k not in ('icons', 'screenshots', 'runs', 'limitations')}, ensure_ascii=False))
