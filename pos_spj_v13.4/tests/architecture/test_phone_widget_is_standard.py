import re
from pathlib import Path

CONFIGURATION_MODULE = Path("pos_spj_v13.4/modulos/configuracion.py")
PHONE_WRAPPER = Path("pos_spj_v13.4/frontend/desktop/components/phone_input.py")


def test_configuracion_uses_phone_widget_for_phones() -> None:
    content = CONFIGURATION_MODULE.read_text(encoding="utf-8")

    assert "from modulos.spj_phone_widget import PhoneWidget" in content
    assert "PhoneInput" not in content
    assert "emp_telefono = QLineEdit" not in content
    assert not re.search(r"telefono\w*\s*=\s*QLineEdit\(", content, re.IGNORECASE)


def test_deprecated_phone_input_wraps_phone_widget() -> None:
    content = PHONE_WRAPPER.read_text(encoding="utf-8")
    assert "from modulos.spj_phone_widget import PhoneWidget" in content
    assert "class PhoneInput(PhoneWidget)" in content
