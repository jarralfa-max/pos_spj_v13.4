import re
from pathlib import Path

CONFIGURATION_MODULE = Path("pos_spj_v13.4/modulos/configuracion.py")


def test_settings_module_uses_standard_company_inputs() -> None:
    content = CONFIGURATION_MODULE.read_text(encoding="utf-8")

    forbidden_patterns = {
        "emp_direccion = QLineEdit": re.compile(r"emp_direccion\s*=\s*QLineEdit\("),
        "emp_tasa_iva = QLineEdit": re.compile(r"emp_tasa_iva\s*=\s*QLineEdit\("),
        "PhoneInput": re.compile(r"PhoneInput"),
    }
    violations = [name for name, pattern in forbidden_patterns.items() if pattern.search(content)]

    assert not violations, "Non-standard company inputs: " + ", ".join(violations)
    assert "AddressAutocompleteInput" in content
    assert "PhoneWidget" in content
    assert "PercentInput" in content
