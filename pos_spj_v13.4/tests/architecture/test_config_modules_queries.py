from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_CONFIG_UI = REPO_ROOT / "pos_spj_v13.4" / "modulos" / "config_modules.py"


def test_config_modules_ui_uses_query_service_for_reads() -> None:
    content = MODULE_CONFIG_UI.read_text(encoding="utf-8")

    assert "from backend.application.queries.module_settings_query_service import ModuleSettingsQueryService" in content
    assert "self.module_settings_query_service = ModuleSettingsQueryService(" in content
    assert "self.module_settings_query_service.list_active_branch_options()" in content
    assert "self.module_settings_query_service.get_branch_feature_flags(suc_id)" in content

    forbidden_fragments = [
        'self.db.execute("SELECT id, nombre FROM sucursales WHERE activa=1 ORDER BY nombre")',
        'self.db.execute("SELECT clave, activo FROM feature_flags")',
    ]
    for fragment in forbidden_fragments:
        assert fragment not in content
