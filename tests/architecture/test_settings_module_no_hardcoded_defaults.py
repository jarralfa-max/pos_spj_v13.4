import re
from pathlib import Path

CONFIGURATION_MODULE = Path("pos_spj_v13.4/modulos/configuracion.py")
FORBIDDEN_SNIPPETS = [
    'QLineEdit("08:00")',
    'QLineEdit("21:00")',
    'QLineEdit("14:00")',
    'QLineEdit("16:00")',
    'setPlainText("Estamos cerrados',
]
FORBIDDEN_SET_VALUES = ["15", "30", "50", "80", "90", "9100"]


def test_settings_module_has_no_arbitrary_ui_defaults() -> None:
    content = CONFIGURATION_MODULE.read_text(encoding="utf-8")
    violations = [snippet for snippet in FORBIDDEN_SNIPPETS if snippet in content]
    for value in FORBIDDEN_SET_VALUES:
        pattern = re.compile(rf"\.setValue\(\s*{re.escape(value)}\s*\)")
        if pattern.search(content):
            violations.append(f"setValue({value})")
    assert not violations, "Hardcoded defaults in Configuración: " + ", ".join(violations)
