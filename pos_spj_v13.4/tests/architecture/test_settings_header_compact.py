from pathlib import Path

CONFIGURATION_MODULE = Path("pos_spj_v13.4/modulos/configuracion.py")


def test_settings_header_uses_compact_page_header() -> None:
    content = CONFIGURATION_MODULE.read_text(encoding="utf-8")

    assert "Configuración del Sistema" not in content
    assert "PageHeader" in content
    assert "⚙️ Configuración" in content
    assert "Empresa, usuarios, permisos, pagos, Happy Hour y cierre mensual." in content
    assert "title.setAlignment(Qt.AlignCenter)" not in content
