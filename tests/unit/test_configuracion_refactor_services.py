from pathlib import Path
import sqlite3
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "pos_spj_v13.4"))

from core.services.configuration_settings_service import (
    CompanyProfileService,
    ModuleSettingsService,
    SystemSettingsService,
)
from repositories.config_repository import ConfigRepository


CONFIG_UI = REPO_ROOT / "pos_spj_v13.4" / "modulos" / "configuracion.py"


def test_configuracion_ui_no_longer_bootstraps_schema_or_defaults() -> None:
    content = CONFIG_UI.read_text(encoding="utf-8")
    bootstrap_method = content[content.index("    def verificar_tablas_configuraciones"):content.index("    def init_ui")]

    assert "CREATE TABLE" not in bootstrap_method
    assert "INSERT OR IGNORE" not in bootstrap_method
    assert "self.conexion.commit" not in bootstrap_method


def test_system_settings_service_reads_and_writes_settings_without_ui_sql() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE configuraciones(clave TEXT PRIMARY KEY, valor TEXT, descripcion TEXT)")
    service = SystemSettingsService(ConfigRepository(conn))

    service.set_setting("tema", "Claro")
    conn.commit()

    assert service.get_setting("tema") == "Claro"
    assert service.get_many(["tema", "faltante"], defaults={"faltante": "0"}) == {"tema": "Claro", "faltante": "0"}


def test_module_settings_service_wraps_module_toggles() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE module_toggles(clave TEXT PRIMARY KEY, activo INTEGER DEFAULT 1, descripcion TEXT DEFAULT '')")
    service = ModuleSettingsService(ConfigRepository(conn))

    service.set_enabled("loyalty", True)
    conn.commit()

    assert service.is_enabled("loyalty") is True
    assert service.get_all()["loyalty_enabled"] is True


def test_company_profile_service_saves_branch_profile() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE sucursales(id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, direccion TEXT, telefono TEXT, activa INTEGER)")
    service = CompanyProfileService(ConfigRepository(conn))

    branch_id = service.save_branch(name="Principal", address="Centro", phone="+5215512345678", active=True)
    conn.commit()

    branch = service.get_branch(branch_id)
    assert branch["nombre"] == "Principal"
    assert branch["telefono"] == "+5215512345678"


def test_configuration_migration_owns_schema_and_default_seed() -> None:
    import importlib

    migration = importlib.import_module("migrations.standalone.096_configuration_services_schema")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE configuraciones(clave TEXT PRIMARY KEY, valor TEXT, descripcion TEXT)")

    migration.run(conn)

    loyalty = conn.execute("SELECT nombre_programa FROM config_programa_fidelidad WHERE id=1").fetchone()
    toggle = conn.execute("SELECT activo FROM module_toggles WHERE clave='loyalty_enabled'").fetchone()
    tax = conn.execute("SELECT valor FROM configuraciones WHERE clave='impuesto_por_defecto'").fetchone()
    assert loyalty["nombre_programa"] == "Programa de Puntos"
    assert toggle["activo"] == 1
    assert tax["valor"] == "16.0"


def test_configuracion_ui_uses_repository_services_instead_of_direct_persistence_calls() -> None:
    content = CONFIG_UI.read_text(encoding="utf-8")

    forbidden_calls = [
        "self.conexion.execute",
        "self.conexion.commit",
        "self.conexion.rollback",
        "cursor.execute",
        "conn.execute",
        "conn.commit",
    ]
    for forbidden_call in forbidden_calls:
        assert forbidden_call not in content


def test_config_repository_owns_remaining_configuration_sql_boundaries() -> None:
    content = (REPO_ROOT / "pos_spj_v13.4" / "repositories" / "config_repository.py").read_text(encoding="utf-8")

    required_methods = [
        "monthly_close_exists",
        "calculate_monthly_close_totals",
        "list_users_v13",
        "save_user_v13",
        "save_role",
        "save_role_permissions",
        "audit_log_rows",
    ]
    for method_name in required_methods:
        assert f"def {method_name}" in content

    removed_methods = [
        "get_legacy_users",
        "save_legacy_user",
        "get_hardware_configs",
        "get_loyalty_weights",
        "list_whatsapp_numbers",
    ]
    for method_name in removed_methods:
        assert f"def {method_name}" not in content

def test_module_config_uses_config_repository_for_toggle_persistence() -> None:
    content = (REPO_ROOT / "pos_spj_v13.4" / "core" / "module_config.py").read_text(encoding="utf-8")

    assert "ConfigRepository" in content
    assert "self.db.execute" not in content
    assert "self.db.commit" not in content
