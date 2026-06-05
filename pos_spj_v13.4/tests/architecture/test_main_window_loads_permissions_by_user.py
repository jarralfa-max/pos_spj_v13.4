from pathlib import Path

MAIN_WINDOW = Path("pos_spj_v13.4/interfaz/main_window.py")
SERVICE = Path("pos_spj_v13.4/core/services/configuration_settings_service.py")
REPOSITORY = Path("pos_spj_v13.4/repositories/config_repository.py")


def test_main_window_uses_user_permissions_not_role_name_for_menu() -> None:
    content = MAIN_WINDOW.read_text(encoding="utf-8")

    assert "permission_codes_for_user(user_id)" in content
    assert "permission_codes_for_role_name(rol)" not in content
    assert 'self.usuario_actual.get("id")' in content


def test_permission_query_and_repository_expose_user_permissions() -> None:
    assert "def permission_codes_for_user" in SERVICE.read_text(encoding="utf-8")
    repo_content = REPOSITORY.read_text(encoding="utf-8")
    assert "def permission_codes_for_user" in repo_content
    assert "SELECT rol FROM usuarios WHERE id=?" in repo_content
