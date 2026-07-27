from pathlib import Path

CONFIGURATION_MODULE = Path("pos_spj_v13.4/modulos/configuracion.py")


def test_settings_dialog_buttons_are_styled_by_helper() -> None:
    lines = CONFIGURATION_MODULE.read_text(encoding="utf-8").splitlines()

    assert "def _style_dialog_buttons" in "\n".join(lines)
    raw_dialog_boxes = [
        (index + 1, line)
        for index, line in enumerate(lines)
        if "QDialogButtonBox(" in line and "_style_dialog_buttons(" not in line
    ]
    assert raw_dialog_boxes == []


def test_settings_dialog_buttons_use_spanish_visible_text() -> None:
    content = CONFIGURATION_MODULE.read_text(encoding="utf-8")

    assert '"Save"' not in content
    assert "'Save'" not in content
    assert '"Cancel"' not in content
    assert "'Cancel'" not in content
    assert '"Guardar"' in content
    assert '"Cancelar"' in content
    assert '"Aceptar"' in content
    assert "primaryBtn" in content
    assert "secondaryBtn" in content
