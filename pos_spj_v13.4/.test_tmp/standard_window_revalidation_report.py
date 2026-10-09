"""Collect the already executed StandardWindow checks; never accepts new debt."""
import hashlib
import html
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE))
from tests.architecture.design_system_audit import BASELINE, regressions, scan_repository, scan_source, summarize

TARGET = PACKAGE / 'docs/refactor/evidence/standard_window_phase_8/revalidation_20261004'
TARGET.mkdir(parents=True, exist_ok=True)

reports = {}
final_cases = {}
for name in ('before', 'crossing-before', 'geometry', 'after', 'geometry-final'):
    date = 'oct05' if name == 'geometry-final' else 'oct04'
    origin = PACKAGE / f'.test_tmp/standard-window-{date}-{name}.xml'
    tree = ET.parse(origin)
    cases = list(tree.getroot().iter('testcase'))
    if name in ('after', 'geometry-final'):
        for case in cases:
            final_cases[(case.get('classname'), case.get('name'))] = case
    reports[name] = {
        'tests': len(cases),
        'passed': sum(not any(case.find(tag) is not None for tag in ('failure', 'error', 'skipped')) for case in cases),
        'failed': sum(case.find('failure') is not None for case in cases),
        'errors': sum(case.find('error') is not None for case in cases),
        'skipped': sum(case.find('skipped') is not None for case in cases),
        'failures': [f"{case.get('classname')}::{case.get('name')}" for case in cases
                     if case.find('failure') is not None or case.find('error') is not None],
    }
    for suffix in ('xml', 'log'):
        shutil.copyfile(origin.with_suffix('.' + suffix), TARGET / f'{name}.{suffix}')

findings = scan_repository()
baseline = json.loads(BASELINE.read_text(encoding='utf-8'))
unallowed, obsolete = regressions(findings, baseline)
changed = 'frontend/desktop/components/standard_window.py'
before_source = subprocess.check_output(
    ['git', 'show', f'HEAD:pos_spj_v13.4/{changed}'], cwd=PACKAGE.parent,
).decode('utf-8-sig')
old_keys = {f.key for f in scan_source(before_source, changed)}
new_source = (PACKAGE / changed).read_text(encoding='utf-8')
added_in_scope = [f.key for f in scan_source(new_source, changed) if f.key not in old_keys]
captures = [
    {'path': p.relative_to(TARGET).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
    for p in sorted((TARGET / 'captures').glob('*.png'))
]
payload = {
    'date': '2026-10-05', 'started_on': '2026-10-04', 'scope': '8. StandardWindow',
    'reports': reports, 'captures': captures,
    'final_distinct_results': {
        'tests': len(final_cases),
        'passed': sum(not any(case.find(tag) is not None for tag in ('failure', 'error', 'skipped'))
                      for case in final_cases.values()),
        'failed': sum(case.find('failure') is not None for case in final_cases.values()),
        'errors': sum(case.find('error') is not None for case in final_cases.values()),
        'skipped': sum(case.find('skipped') is not None for case in final_cases.values()),
    },
    'capture_count': len(captures),
    'new_violations_in_changed_window': added_in_scope,
    'repository_audit': {
        'rules': summarize(findings), 'occurrences': len(findings),
        'allowed_occurrences': len(findings) - sum(unallowed.values()),
        'outside_baseline': [{'path': key[0], 'rule': key[1], 'fingerprint': key[2], 'count': count}
                             for key, count in unallowed.items()],
        'obsolete_baseline_occurrences': sum(obsolete.values()),
    },
    'limitations': ['Qt offscreen; simulated monitor areas, not physical monitor/DPI certification.',
                    'Captures are review evidence, not an approved pixel comparison.',
                    'Pre-existing work from other phases remains outside this validation scope.'],
}
(TARGET / 'validation.json').write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
for name in ('standard_window_drag_review.py', 'standard_window_drag_review.log',
             'standard_window_drag_review-after.log'):
    shutil.copyfile(PACKAGE / '.test_tmp' / name, TARGET / name)
figures = '\n'.join(
    f'<figure><a href="{html.escape(item["path"])}"><img loading="lazy" src="{html.escape(item["path"])}" alt="{html.escape(Path(item["path"]).stem)}"></a><figcaption>{html.escape(Path(item["path"]).stem)}</figcaption></figure>'
    for item in captures
)
document = f'''<!doctype html><html lang="es"><meta charset="utf-8">
<title>StandardWindow · validación 2026-10-05</title>
<style>body{{font:16px system-ui;margin:2rem;background:#eee;color:#222}}main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:1rem}}figure{{margin:0;padding:1rem;background:white}}img{{width:100%;height:auto}}figcaption{{overflow-wrap:anywhere}}</style>
<h1>StandardWindow · 5 de octubre de 2026</h1>
<p>{len(captures)} capturas: cinco áreas disponibles, Claro/Oscuro y tres densidades.</p>
<p>Qt offscreen, fuentes reales y monitores simulados. No es una comparación contra píxeles aprobados.</p>
<p><a href="validation.json">Resultados finales y hashes</a> · <a href="after.xml">Regresión completa</a> · <a href="geometry-final.xml">Geometría final</a></p>
<main>{figures}</main></html>'''
(TARGET / 'index.html').write_text(document, encoding='utf-8')
print(json.dumps({k: v for k, v in payload.items() if k != 'captures'}, ensure_ascii=True, indent=2))
