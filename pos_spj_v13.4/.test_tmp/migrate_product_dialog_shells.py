import ast
import json
import re
from pathlib import Path

root = Path('frontend/desktop/modules/products/dialogs')
report = []
for path in sorted(root.glob('*.py')):
    raw = path.read_bytes()
    source = raw.decode('utf-8')
    newline = '\r\n' if '\r\n' in source else '\n'
    source = source.replace('\r\n', '\n')
    tree = ast.parse(source)
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)
               and any(isinstance(base, ast.Name) and base.id == 'QDialog' for base in node.bases)]
    if not classes:
        continue
    edits = []
    for cls in classes:
        init = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == '__init__')
        old = ast.get_source_segment(source, init)
        minimum = re.search(r'self.setMinimum(?:Width|Size)\((\d+)', old)
        width = int(minimum[1]) if minimum else 420
        new = old.replace('super().__init__(parent)', f'super().__init__(parent, width={width})', 1)
        assert new != old, cls.name
        assert new.count('layout = QVBoxLayout(self)') == 1, cls.name
        new = new.replace('layout = QVBoxLayout(self)', 'layout = self.content_layout()')
        footer = re.findall(r'        layout.addWidget\((buttons|close)\)', new)
        assert len(footer) == 1, cls.name
        new = new.replace(f'layout.addWidget({footer[0]})', f'self.add_footer_widget({footer[0]})')
        native_ok = '        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)\n        buttons.accepted'
        if native_ok in new:
            new = new.replace(native_ok, '        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)\n        buttons.button(QDialogButtonBox.Ok).setText("Aceptar")\n        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")\n        buttons.accepted')
        if path.name == 'purchase_units_dialog.py':
            new = new.replace('        buttons.rejected.connect(self.reject)', '        buttons.button(QDialogButtonBox.Close).setText("Cerrar")\n        buttons.rejected.connect(self.reject)')
        edits.append((old, new))
        report.append({'path': path.as_posix(), 'class': cls.name, 'width': width})
    changed = source
    for old, new in edits:
        assert changed.count(old) == 1
        changed = changed.replace(old, new)
    changed = changed.replace('(QDialog):', '(StandardDialog):')
    changed = changed.replace('    QDialog,\n', '')
    if not any(isinstance(n, ast.Name) and n.id == 'QVBoxLayout' for n in ast.walk(ast.parse(changed))):
        changed = changed.replace('    QVBoxLayout,\n', '')
    anchor = 'from __future__ import annotations\n'
    changed = changed.replace(anchor, anchor + '\nfrom frontend.desktop.components.dialogs import StandardDialog\n', 1)
    def preserved_methods(parsed):
        result = {}
        for item in parsed.body:
            if isinstance(item, ast.FunctionDef):
                result[item.name] = ast.dump(item, include_attributes=False)
            elif isinstance(item, ast.ClassDef):
                for method in item.body:
                    if isinstance(method, ast.FunctionDef) and method.name != '__init__':
                        result[f'{item.name}.{method.name}'] = ast.dump(method, include_attributes=False)
        return result
    assert preserved_methods(tree) == preserved_methods(ast.parse(changed)), path
    path.write_bytes(changed.replace('\n', newline).encode('utf-8'))
assert len(report) == 22, len(report)
Path('.test_tmp/products-dialog-shell-migration.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({'dialogs': len(report), 'files': len({item['path'] for item in report}), 'non_constructor_methods': 'identical AST'}, indent=2))
