"""Collect existing phase 9 evidence without rerunning or changing tests."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

from tests.architecture.design_system_audit import regressions, scan_repository, summarize

ROOT = Path.cwd()
TMP = ROOT / '.test_tmp'
DEST = ROOT / 'docs/refactor/evidence/standard_dialog_phase_9'
DEST.mkdir(parents=True, exist_ok=True)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(name):
    source = TMP / name
    target = DEST / name
    shutil.copy2(source, target)
    return target


def cases(path):
    result = []
    for node in ET.parse(path).iter('testcase'):
        status = next((tag for tag in ('failure', 'error', 'skipped') if node.find(tag) is not None), 'passed')
        result.append({'id': node.attrib['classname'] + '::' + node.attrib['name'], 'status': status})
    return result


baseline_stems = [
    'standard-dialog-before', 'standard-dialog-geometry-before',
    'standard-dialog-finance-hr-before', 'standard-dialog-finance-hr-before-recheck',
    'standard-dialog-visuals-before', 'dialog-baseline-six',
]
final_stems = [
    'standard-dialog-regression', 'standard-dialog-contracts',
    'standard-dialog-finance-hr-after', 'standard-dialog-visuals-final',
    'standard-dialog-finance-hr-architecture', 'standard-dialog-final',
]
runs = []
latest = {}
for stem in baseline_stems + final_stems:
    xml = export(stem + '.xml')
    log = export(stem + '.log')
    items = cases(xml)
    runs.append({
        'name': stem, 'category': 'baseline' if stem in baseline_stems else 'validation',
        'counts': dict(Counter(item['status'] for item in items)),
        'xml': xml.name, 'log': log.name,
        'xml_sha256': digest(xml), 'recorded_at_utc': datetime.fromtimestamp(xml.stat().st_mtime, timezone.utc).isoformat(),
    })
    if stem in final_stems:
        for item in items:
            latest[item['id']] = dict(item, run=stem)

for name in ('dialog-baseline-proof.json', 'dialog-baseline-comparison.json',
             'dialog_baseline_plugin.py', 'dialog_baseline_compare.py',
             'standard-dialog-additional-failures.json', 'standard-dialog-audit-before.json',
             'standard-dialog-audit-after.json'):
    export(name)

before = json.loads((TMP / 'standard-dialog-audit-before.json').read_text(encoding='utf-8'))
findings = scan_repository()
baseline = json.loads((ROOT / 'tests/architecture/design_system_debt_baseline.json').read_text(encoding='utf-8'))
outside, stale = regressions(findings, baseline)


def key(item):
    return item['path'], item['rule'], item['fingerprint']


before_count = Counter(key(item) for item in before['findings'])
after_count = Counter(item.key for item in findings)
scope = {
    'frontend/desktop/components/dialogs.py',
    'frontend/desktop/modules/finance/dialogs/_form_dialog.py',
    'frontend/desktop/modules/hr/dialogs/_form_dialog.py',
}
introduced = after_count - before_count
resolved = before_count - after_count
assert not [entry for entry in introduced if entry[0] in scope]
for path in scope - {'frontend/desktop/components/dialogs.py'}:
    assert not any(entry['path'] == path for entry in baseline['findings'])
    assert not any(item.path == path for item in findings)

audit = {
    'before_total': sum(before_count.values()), 'after_total': len(findings),
    'after_rules': summarize(findings),
    'outside_allowlist': [{'key': list(entry), 'count': count} for entry, count in outside.items()],
    'stale_allowlist': [{'key': list(entry), 'count': count} for entry, count in stale.items()],
    'introduced_since_before': [{'key': list(entry), 'count': count} for entry, count in introduced.items()],
    'resolved_since_before': [{'key': list(entry), 'count': count} for entry, count in resolved.items()],
    'new_in_phase_scope': 0,
    'removed_allowlist_paths': sorted(scope - {'frontend/desktop/components/dialogs.py'}),
    'note': 'The full-tree delta includes concurrent CRM changes; see standard-dialog-additional-failures.json.',
}

source_paths = sorted(scope | {
    'frontend/desktop/design_system/component_contracts.py',
    'frontend/desktop/design_system/migration_guide.md',
    'frontend/desktop/design_system/visual_guidelines.md',
    'frontend/desktop/components/page_viewport.py',
    'frontend/desktop/themes/qss_builder.py',
    'frontend/desktop/themes/theme_manager.py',
    'frontend/desktop/themes/tokens.py',
    'tests/architecture/design_system_debt_baseline.json',
    'tests/ui/test_standard_dialog_geometry.py',
    'tests/ui/test_finance_hr_standard_dialogs.py',
    'tests/ui/test_standard_dialog_visuals.py',
})
captures = sorted((DEST / 'captures').glob('*.png'))
assert len(captures) == 54, len(captures)
current = cases(TMP / 'standard-dialog-final.xml')
assert len(current) == 63 and all(item['status'] == 'passed' for item in current)
payload = {
    'phase': '9. StandardDialog', 'closed_on': '2026-10-09',
    'git_head': subprocess.check_output(['git', '-C', str(ROOT.parent), 'rev-parse', 'HEAD'], text=True).strip(),
    'runs': runs, 'latest_distinct_counts': dict(Counter(item['status'] for item in latest.values())),
    'latest_distinct_cases': sorted(latest.values(), key=lambda item: item['id']),
    'current_core_counts': dict(Counter(item['status'] for item in current)),
    'audit': audit, 'source_sha256': {path: digest(ROOT / path) for path in source_paths},
    'captures': [{'path': path.relative_to(DEST).as_posix(), 'sha256': digest(path)} for path in captures],
    'limits': [
        'Core 63 cases and 54 images revalidated on October 9; broader segments were run on October 7-8.',
        'Qt offscreen with real fonts and simulated monitor work areas; no physical mixed-DPI verification.',
        'Eleven failures in the broader segments are documented; the full repository suite is not green.',
        'No database migration or business-rule changes belong to this phase.',
    ],
}
(DEST / 'validation.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
figures = '\n'.join(
    '<figure><a href="' + path.relative_to(DEST).as_posix() + '"><img loading="lazy" src="' + path.relative_to(DEST).as_posix()
    + '" alt="' + html.escape(path.stem) + '"></a><figcaption>' + html.escape(path.stem) + '</figcaption></figure>'
    for path in captures
)
(DEST / 'index.html').write_text('''<!doctype html>
<html lang="es"><meta charset="utf-8"><title>StandardDialog — evidencia fase 9</title>
<style>body{font:16px system-ui;margin:2rem;background:#f6f6f6;color:#222}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:1rem}figure{margin:0;padding:1rem;background:white}img{max-width:100%;height:auto}figcaption{overflow-wrap:anywhere}</style>
<h1>StandardDialog · 9 de octubre de 2026</h1>
<p>54 capturas: matriz de cinco resoluciones, dos temas y tres densidades (30), más formularios Finanzas/RR. HH. a 640×480 antes y después del scroll (24).</p>
<p>63 pruebas específicas aprobadas. Qt offscreen con fuentes reales y áreas de monitor simuladas; inspección de muestras, sin certificación de hardware ni comparación de píxeles aprobados.</p>
<p><a href="validation.json">Resultados, fallos externos y hashes</a> · <a href="../../standard_dialog_phase_9.md">Informe de la fase</a></p><main>
''' + figures + '\n</main></html>\n', encoding='utf-8')
print(json.dumps({'distinct': payload['latest_distinct_counts'], 'core': payload['current_core_counts'],
                  'captures': len(captures), 'audit': audit}, ensure_ascii=False))
