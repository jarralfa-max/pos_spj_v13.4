from pathlib import Path

CONFIGURATION_MODULE = Path("pos_spj_v13.4/modulos/configuracion.py")
UI_COMPONENTS = Path("pos_spj_v13.4/modulos/ui_components.py")


def test_settings_uses_compact_page_header() -> None:
    content = CONFIGURATION_MODULE.read_text(encoding="utf-8")

    assert "PageHeader(" in content
    assert "compact=True" in content
    assert "Configuración del Sistema" not in content
    assert "setAlignment(Qt.AlignCenter)" not in content


def test_page_header_supports_compact_mode() -> None:
    content = UI_COMPONENTS.read_text(encoding="utf-8")

    assert "compact: bool = False" in content
    assert 'self.setProperty("compact", compact)' in content
    assert "self.setMaximumHeight(90)" in content
    assert "self.setMinimumHeight(56)" in content
