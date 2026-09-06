from pathlib import Path
from tests.architecture.architecture_guardrails import APP_ROOT

CONFIGURATION_MODULE = (APP_ROOT / "modulos/configuracion.py")


def test_settings_module_does_not_hardcode_permission_matrix() -> None:
    content = CONFIGURATION_MODULE.read_text(encoding="utf-8")
    forbidden = [token for token in ["MODULOS = [", "ACCIONES = ["] if token in content]
    assert not forbidden, "Hardcoded permission matrix in Configuración: " + ", ".join(forbidden)
