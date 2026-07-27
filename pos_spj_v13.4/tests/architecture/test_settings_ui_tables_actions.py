from pathlib import Path

CONFIGURATION_MODULE = Path("pos_spj_v13.4/modulos/configuracion.py")


def test_settings_tables_use_standard_action_helpers() -> None:
    content = CONFIGURATION_MODULE.read_text(encoding="utf-8")

    assert "setFixedSize(26, 24)" not in content
    assert "setFixedSize(26,24)" not in content
    assert "def _setup_table_defaults" in content
    assert "verticalHeader().setDefaultSectionSize(44)" in content
    assert "def _create_action_button" in content
    assert "warningBtn" in content
    assert "successBtn" in content
    assert "dangerBtn" in content


def test_settings_action_columns_have_minimum_width() -> None:
    content = CONFIGURATION_MODULE.read_text(encoding="utf-8")

    assert "table.setColumnWidth(actions_column, 120)" in content
    assert "actions_column=5" in content
    assert "actions_column=6" in content
    assert "actions_column=3" in content
