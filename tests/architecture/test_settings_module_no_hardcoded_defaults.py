import re
from pathlib import Path

CONFIGURATION_MODULE = Path("pos_spj_v13.4/modulos/configuracion.py")
FORBIDDEN_DEFAULTS = ["1", "7", "10", "15", "30", "50", "80", "90", "100", "9100", "0.5"]


def test_settings_module_has_no_arbitrary_set_value_defaults() -> None:
    content = CONFIGURATION_MODULE.read_text(encoding="utf-8")
    violations = []
    for value in FORBIDDEN_DEFAULTS:
        pattern = re.compile(rf"\.setValue\(\s*{re.escape(value)}\s*\)")
        if pattern.search(content):
            violations.append(f"setValue({value})")
    assert not violations, "Hardcoded numeric defaults in Configuración: " + ", ".join(violations)
