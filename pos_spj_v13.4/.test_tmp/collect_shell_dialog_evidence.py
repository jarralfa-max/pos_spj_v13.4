"""Collect StandardDialog shell adoption results; never executes tests."""
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

from tests.architecture.design_system_audit import BASELINE, regressions, scan_repository, summarize

ROOT = Path.cwd()
TMP = ROOT / '.test_tmp'
DEST = ROOT / 'docs/refactor/evidence/standard_dialog_phase_9/shell_adoption_20261010'
DEST.mkdir(parents=True, exist_ok=True)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(path, name=None):
    target = DEST / (name or path.name)
    shutil.copy2(path, target)
    return target


def cases(path):
    result = []
    for case in ET.parse(path).iter('testcase'):
        status = next((tag for tag in ('failure', 'error', 'skipped') if case.find(tag) is not None), 'passed')
        result.append({'id': case.attrib['classname'] + '::' + case.attrib['name'], 'status': status})
    return result


runs, latest = [], {}
for path in sorted(TMP.glob('shell-dialog-*.xml'), key=lambda path: path.stat().st_mtime):
    category = 'baseline' if 'before' in path.stem else 'validation'
    items = cases(path)
    target_name = path.name
    if path.stem in ('shell-dialog-prompts-before', 'shell-dialog-prompts-after'):
        assert any('test_shell_prompt_adoption' in item['id'] for item in items)
        target_name = path.name.replace('shell-dialog-prompts-', 'shell-dialog-page-prompts-')
    xml = export(path, target_name)
    log_path = path.with_suffix('.log')
    if log_path.exists():
        export(log_path, Path(target_name).with_suffix('.log').name)
    runs.append({'name': xml.stem, 'category': category,
                 'counts': dict(Counter(item['status'] for item in items)),
                 'timestamp_utc': datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                 'xml_sha256': digest(xml)})
    if category == 'validation':
        for item in items:
            latest[item['id']] = dict(item, run=xml.stem)

counts = Counter(item['status'] for item in latest.values())
assert counts['error'] == counts['skipped'] == 0, counts
assert counts['failure'] == 2, counts
assert {item['id'].split('::')[-1] for item in latest.values() if item['status'] == 'failure'} == {
    'test_desktop_visual_debt_does_not_grow', 'test_visual_debt_baseline_is_exact_and_kept_pruned'}

before = json.loads((TMP / 'standard-dialog-audit-after.json').read_text(encoding='utf-8'))
findings = scan_repository()
after = {'rules': summarize(findings), 'findings': [asdict(item) for item in findings]}
(DEST / 'audit-after.json').write_text(json.dumps(after, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
export(TMP / 'standard-dialog-audit-after.json', 'audit-before.json')
baseline = json.loads(BASELINE.read_text(encoding='utf-8'))
outside, stale = regressions(findings, baseline)
removed = json.loads((TMP / 'shell-dialog-allowlist-removed.json').read_text(encoding='utf-8'))
assert len(removed) == 32
assert not any(item.rule == 'noncanonical_dialog' for item in findings)

def finding_key(item):
    return item['path'], item['rule'], item['fingerprint']

before_count = Counter(finding_key(item) for item in before['findings'])
after_count = Counter(item.key for item in findings)
assert not after_count - before_count, after_count - before_count

for name in ('shell-dialog-allowlist-removed.json', 'shell-dialog-operations-preservation.json',
             'products-dialog-shell-migration.json'):
    export(TMP / name)
module_sources = {item['path'] for item in before['findings'] if item['rule'] == 'noncanonical_dialog'}
prompt_sources = {
    'frontend/desktop/modules/' + path for path in (
        'products/pages/branch_channel_page.py', 'purchasing/pages/enterprise_pages.py',
        'hr/pages/employees_page.py', 'meat_processing/pages/quality_inspection_page.py',
        'meat_processing/pages/production_plan_page.py', 'finance/pages/bank_reconciliation_page.py',
        'finance/pages/accounts_receivable_page.py', 'configuracion/pages/pantalla_cliente_page.py')}
source_paths = module_sources | prompt_sources | {
    'frontend/desktop/components/dialogs.py', 'frontend/desktop/components/numeric_keypad_dialog.py',
    'frontend/desktop/design_system/migration_guide.md',
    'tests/architecture/design_system_debt_baseline.json',
    'tests/architecture/test_standard_dialog_ownership.py',
    'tests/integration/meat_processing/test_quality_inspection_page.py',
    'tests/ui/test_standard_dialog_footer.py', 'tests/ui/test_numeric_keypad_standard_dialog.py',
    'tests/ui/test_standard_dialog_prompts.py', 'tests/ui/test_shell_prompt_adoption.py',
    'tests/ui/test_products_standard_dialog_adoption.py',
    'tests/ui/test_finance_remaining_standard_dialogs.py', 'tests/ui/test_operations_standard_dialogs.py',
}
for name in source_paths:
    if name.endswith('.py'):
        compile((ROOT / name).read_text(encoding='utf-8-sig'), name, 'exec')

for path in (ROOT / 'docs/refactor/evidence/standard_dialog_shell_adoption/captures').glob('*.png'):
    shutil.copy2(path, DEST / 'captures' / path.name)
captures = sorted((DEST / 'captures').glob('*.png'))
assert len(captures) == 123, len(captures)
payload = {
    'phase': '9. StandardDialog — shell module adoption', 'closed_on': '2026-10-13',
    'git_head': subprocess.check_output(['git', '-C', str(ROOT.parent), 'rev-parse', 'HEAD'], text=True).strip(),
    'scope': {'module_native_dialog_bases_migrated': 33, 'module_files': len(module_sources),
              'shared_numeric_dialog_migrated': True, 'native_prompt_calls_migrated': 10,
              'prompt_files': 8, 'shell_modules_scanned': 17},
    'runs': runs, 'latest_distinct_counts': dict(counts),
    'latest_distinct_cases': sorted(latest.values(), key=lambda item: item['id']),
    'audit': {'before_count': sum(before_count.values()), 'after_count': len(findings),
              'new_findings': [], 'resolved_count': sum((before_count-after_count).values()),
              'allowlist_entries_removed': len(removed),
              'outside_allowlist': [{'key': list(key), 'count': count} for key, count in outside.items()],
              'stale_allowlist': [{'key': list(key), 'count': count} for key, count in stale.items()]},
    'source_sha256': {name: digest(ROOT / name) for name in sorted(source_paths)},
    'captures': [{'path': path.relative_to(DEST).as_posix(), 'sha256': digest(path)} for path in captures],
    'limits': [
        'Results span October 9–13. Current sources preserve concurrent edits outside this UI task.',
        'The initial mixed test run reported 53 missing-fixture errors; all affected cases passed in the later UI segment.',
        'Two global guardrails still fail on existing unrelated visual debt and a stale CRM allowlist path.',
        'Images use Qt offscreen with real fonts and simulated work areas, not physical mixed-DPI hardware.',
        'Native file pickers and QMessageBox alerts are outside the custom dialog ownership rule.',
    ],
}
(DEST / 'validation.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
figures = '\n'.join('<figure><a href="'+p.relative_to(DEST).as_posix()+'"><img loading="lazy" src="'
                    +p.relative_to(DEST).as_posix()+'" alt="'+html.escape(p.stem)+'"></a><figcaption>'
                    +html.escape(p.stem)+'</figcaption></figure>' for p in captures)
(DEST / 'index.html').write_text('''<!doctype html>
<html lang="es"><meta charset="utf-8"><title>StandardDialog en el shell</title>
<style>body{font:16px system-ui;margin:2rem;background:#f6f6f6;color:#222}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:1rem}figure{margin:0;padding:1rem;background:white}img{max-width:100%;height:auto}figcaption{overflow-wrap:anywhere}</style>
<h1>StandardDialog en los módulos del shell</h1><p>Cierre: 13 de octubre de 2026. 123 capturas de Qt offscreen; monitores simulados y fuentes reales. Revisión de muestras, sin comparación contra píxeles aprobados ni certificación de hardware.</p>
<p><a href="validation.json">Resultados y hashes</a> · <a href="../../../standard_dialog_shell_adoption.md">Informe</a></p><main>
''' + figures + '\n</main></html>\n', encoding='utf-8')
print(json.dumps({'distinct': dict(counts), 'captures': len(captures), 'sources': len(source_paths),
                  'before': sum(before_count.values()), 'after': len(findings),
                  'outside_allowlist': sum(outside.values()), 'resolved': sum((before_count-after_count).values())}))
