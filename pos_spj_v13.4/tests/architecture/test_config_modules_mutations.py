from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_CONFIG_UI = REPO_ROOT / "pos_spj_v13.4" / "modulos" / "config_modules.py"


def test_config_modules_ui_uses_service_boundary_for_mutations() -> None:
    content = MODULE_CONFIG_UI.read_text(encoding="utf-8")

    required_fragments = [
        "from core.services.feature_flag_service import FeatureFlagService",
        "from repositories.feature_flag_repository import FeatureFlagRepository",
        "self.feature_flag_service = getattr(container, 'feature_flag_service', None)",
        "self.feature_flag_service = FeatureFlagService(FeatureFlagRepository(self.db))",
        "self.feature_flag_service.set_flag(codigo, suc_id, activo)",
    ]
    for fragment in required_fragments:
        assert fragment in content

    forbidden_fragments = [
        "ffs.repo.set_flag(",
        "ffs._cache.pop(",
        "INSERT INTO feature_flags",
        "ON CONFLICT(clave) DO UPDATE SET activo=excluded.activo",
        "self.db.commit()",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in content
