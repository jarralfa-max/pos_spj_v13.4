from pathlib import Path

CONFIGURATION_MODULE = Path("pos_spj_v13.4/modulos/configuracion.py")


def test_settings_module_does_not_hardcode_permission_matrix() -> None:
    content = CONFIGURATION_MODULE.read_text(encoding="utf-8")
    forbidden = [token for token in ["MODULOS = [", "ACCIONES = ["] if token in content]
    assert not forbidden, "Hardcoded permission matrix in Configuración: " + ", ".join(forbidden)
