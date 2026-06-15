from pathlib import Path
import sqlite3
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "pos_spj_v13.4"))

from core.services.configuration_settings_service import (
    CompanyProfileService,
    ModuleSettingsService,
    PermissionEventPublisher,
    SystemSettingsService,
)
from repositories.config_repository import ConfigRepository


CONFIG_UI = REPO_ROOT / "pos_spj_v13.4" / "modulos" / "configuracion.py"


def test_configuracion_ui_no_longer_bootstraps_schema_or_defaults() -> None:
    content = CONFIG_UI.read_text(encoding="utf-8")

    assert "def verificar_tablas_configuraciones" not in content
    assert "settings_application_service.assert_ready()" in content
    assert "CREATE TABLE" not in content
    assert "INSERT OR IGNORE" not in content
    assert "self.conexion.commit" not in content


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
        "permission_matrix",
        "list_happy_hour_rules",
        "save_happy_hour_rule",
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


def test_configuracion_operation_ids_use_canonical_uuidv7_generator() -> None:
    content = CONFIG_UI.read_text(encoding="utf-8")

    assert "from backend.shared.ids import new_uuid" in content
    assert "from uuid import uuid4" not in content
    assert "return new_uuid()" in content


def test_config_repository_removed_unused_legacy_branch_identity_helpers() -> None:
    content = (REPO_ROOT / "pos_spj_v13.4" / "repositories" / "config_repository.py").read_text(encoding="utf-8")

    assert "def create_branch" not in content
    assert "def update_branch" not in content
    assert "def disable_branch" not in content



def test_permission_event_publisher_adds_uuidv7_event_id_to_fallback_event() -> None:
    publisher = PermissionEventPublisher()

    publisher.publish(
        "ROLE_PERMISSIONS_UPDATED",
        operation_id="019b17a7-0000-7000-8000-000000000001",
        entity_id="019b17a7-0000-7000-8000-000000000002",
        user_name="admin",
        payload={"branch_id": "019b17a7-0000-7000-8000-000000000003"},
    )

    event = publisher.published_events[0]
    assert event["event_id"][14] == "7"
    assert event["event_id"] == event["event_id"].lower()

def test_permission_event_publisher_uses_uuidv7_branch_id_for_branch_agnostic_events() -> None:
    publisher = PermissionEventPublisher()

    publisher.publish(
        "ROLE_PERMISSIONS_UPDATED",
        operation_id="019b17a7-0000-7000-8000-000000000011",
        entity_id="019b17a7-0000-7000-8000-000000000012",
        user_name="admin",
        payload={"role_id": "019b17a7-0000-7000-8000-000000000013"},
    )

    event = publisher.published_events[0]
    assert event["branch_id"][14] == "7"
    assert event["branch_id"] == event["branch_id"].lower()


def test_permission_event_publisher_does_not_default_branch_identity_to_integer_one() -> None:
    content = (REPO_ROOT / "pos_spj_v13.4" / "core" / "services" / "configuration_settings_service.py").read_text(encoding="utf-8")

    assert 'payload.get("branch_id", "1")' not in content
    assert 'payload.get("branch_id") or payload.get("sucursal_id")' in content

def test_permission_event_publisher_rejects_legacy_operation_id_strings() -> None:
    publisher = PermissionEventPublisher()

    try:
        publisher.publish(
            "ROLE_PERMISSIONS_UPDATED",
            operation_id="op-save-permissions",
            entity_id="019b17a7-0000-7000-8000-000000000022",
            user_name="admin",
            payload={"branch_id": "019b17a7-0000-7000-8000-000000000023"},
        )
    except ValueError as exc:
        assert "operation_id" in str(exc)
    else:
        raise AssertionError("legacy operation_id strings must be rejected")

def test_permission_event_publisher_rejects_integer_branch_identity() -> None:
    publisher = PermissionEventPublisher()

    try:
        publisher.publish(
            "USER_PERMISSIONS_UPDATED",
            operation_id="019b17a7-0000-7000-8000-000000000031",
            entity_id="019b17a7-0000-7000-8000-000000000032",
            user_name="admin",
            payload={"branch_id": 1},
        )
    except ValueError as exc:
        assert "branch_id" in str(exc)
    else:
        raise AssertionError("integer branch_id values must be rejected")



def test_configuracion_permission_events_do_not_publish_integer_entity_id_payloads() -> None:
    content = (
        REPO_ROOT / "pos_spj_v13.4" / "core" / "services" / "configuration_settings_service.py"
    ).read_text(encoding="utf-8")

    forbidden_patterns = [
        "entity_id=str(user_id)",
        "entity_id=str(role_id)",
        "entity_id=str(saved_id)",
        'payload={"user_id": user_id',
        'payload={"role_id": role_id',
        'payload={"role_id": saved_id',
    ]
    for pattern in forbidden_patterns:
        assert pattern not in content


def test_config_repository_can_resolve_event_labels_without_exposing_integer_ids() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE usuarios(id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT);
        CREATE TABLE roles(id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, descripcion TEXT);
        INSERT INTO usuarios(usuario) VALUES('ana');
        INSERT INTO roles(nombre, descripcion) VALUES('gerente', 'Gerente');
        """
    )
    repository = ConfigRepository(conn)

    assert repository.username_for_id(1) == "ana"
    assert repository.role_name_for_id(1) == "gerente"


def test_permission_event_publisher_rejects_legacy_entity_id_strings() -> None:
    publisher = PermissionEventPublisher()

    try:
        publisher.publish(
            "ROLE_PERMISSIONS_UPDATED",
            operation_id="019b17a7-0000-7000-8000-000000000041",
            entity_id="admin",
            user_name="admin",
            payload={"branch_id": "019b17a7-0000-7000-8000-000000000043"},
        )
    except ValueError as exc:
        assert "entity_id" in str(exc)
    else:
        raise AssertionError("legacy entity_id strings must be rejected")
