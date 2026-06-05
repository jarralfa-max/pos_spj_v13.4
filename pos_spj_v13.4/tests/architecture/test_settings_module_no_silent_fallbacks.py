import re
from pathlib import Path

CONFIGURATION_MODULE = Path("pos_spj_v13.4/modulos/configuracion.py")

SILENT_EXCEPTION_PATTERNS = [
    re.compile(r"except\s+Exception\s*:\s*pass"),
    re.compile(r"except\s+Exception\s*:\s*return"),
    re.compile(r"except\s+Exception\s*:\s*\n\s*return\b"),
    re.compile(r"except\s+Exception\s*:\s*\n\s*pass\b"),
]


def test_settings_module_has_no_silent_exception_branches() -> None:
    content = CONFIGURATION_MODULE.read_text(encoding="utf-8")
    violations = [pattern.pattern for pattern in SILENT_EXCEPTION_PATTERNS if pattern.search(content)]
    assert not violations, "Silent exception branches in Configuración: " + ", ".join(violations)
