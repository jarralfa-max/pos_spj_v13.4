from pathlib import Path
import sqlite3
import sys
import importlib

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "pos_spj_v13.4"))

from backend.shared.ids import new_uuid
from core.services.configuration_settings_service import (
    CompanyProfileService,
    ModuleSettingsService,
    PermissionEventPublisher,
    SystemSettingsService,
)
from repositories.config_repository import ConfigRepository


CONFIG_UI = REPO_ROOT / "pos_spj_v13.4" / "modulos" / "configuracion.py"
CONFIG_SERVICE = REPO_ROOT / "pos_spj_v13.4" / "core" / "services" / "configuration_settings_service.py"
CONFIG_REPOSITORY = REPO_ROOT / "pos_spj_v13.4" / "repositories" / "config_repository.py"


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


<<<<<<< HEAD
def test_company_profile_service_saves_branch_profile() -> None:
    from uuid import UUID

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # Canonical post-migration-101 schema: sucursales carries a uuid identity.
    conn.execute(
        "CREATE TABLE sucursales(id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, "
        "nombre TEXT, direccion TEXT, telefono TEXT, activa INTEGER)"
    )
=======
def test_company_profile_service_saves_branch_profile_with_uuid_identity() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE sucursales(id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, nombre TEXT, direccion TEXT, telefono TEXT, activa INTEGER)")
>>>>>>> claude/intelligent-clarke-uq1ck7
    service = CompanyProfileService(ConfigRepository(conn))

    branch_id = service.save_branch(name="Principal", address="Centro", phone="+5215512345678", active=True)
    conn.commit()

    # save_branch must mint a canonical UUIDv7 identity, never an integer id.
    assert UUID(branch_id).version == 7
    assert branch_id == branch_id.lower()

    branch = service.get_branch(branch_id)
    assert branch["uuid"] == branch_id
    assert branch["nombre"] == "Principal"
    assert branch["telefono"] == "+5215512345678"
    assert branch["uuid"] == branch_id


def test_configuration_migration_owns_schema_default_seed_and_uuid_backfill() -> None:
    migration = importlib.import_module("migrations.standalone.096_configuration_services_schema")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE configuraciones(clave TEXT PRIMARY KEY, valor TEXT, descripcion TEXT);
        CREATE TABLE sucursales(id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, direccion TEXT, telefono TEXT, activa INTEGER DEFAULT 1);
        CREATE TABLE roles(id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT UNIQUE, descripcion TEXT);
        CREATE TABLE usuarios(id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT, nombre TEXT, email TEXT, rol TEXT, sucursal_id INTEGER, activo INTEGER DEFAULT 1, empleado_id INTEGER, password_hash TEXT);
        CREATE TABLE rol_permisos(rol_id INTEGER, modulo TEXT, accion TEXT, permitido INTEGER);
        CREATE TABLE personal(id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, apellidos TEXT, activo INTEGER DEFAULT 1, usuario_id INTEGER);
        CREATE TABLE audit_logs(fecha TEXT, usuario TEXT, modulo TEXT, accion TEXT, detalles TEXT);
        CREATE TABLE cierre_mensual(id INTEGER PRIMARY KEY AUTOINCREMENT, periodo TEXT, cerrado_por TEXT, fecha_cierre TEXT, total_ventas REAL, total_compras REAL, total_merma REAL, sucursal_id INTEGER);
        CREATE TABLE happy_hour_rules(id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, hora_inicio TEXT, hora_fin TEXT, dias_semana TEXT, tipo_descuento TEXT, valor REAL, aplica_a TEXT, aplica_valor TEXT, mensaje_wa TEXT, activo INTEGER, sucursal_id INTEGER);
        INSERT INTO sucursales(nombre, direccion, telefono, activa) VALUES('Principal', 'Centro', '+5215512345678', 1);
        INSERT INTO roles(nombre, descripcion) VALUES('admin', 'Administrador');
        INSERT INTO usuarios(usuario, nombre, email, rol, sucursal_id, activo) VALUES('ana', 'Ana', 'ana@example.com', 'admin', 1, 1);
        INSERT INTO rol_permisos(rol_id, modulo, accion, permitido) VALUES(1, 'CONFIGURACION', 'ver', 1);
        """
    )

    migration.run(conn)

    loyalty = conn.execute("SELECT nombre_programa FROM config_programa_fidelidad WHERE id=1").fetchone()
    toggle = conn.execute("SELECT activo FROM module_toggles WHERE clave='loyalty_enabled'").fetchone()
    tax = conn.execute("SELECT valor FROM configuraciones WHERE clave='impuesto_por_defecto'").fetchone()
    branch_uuid = conn.execute("SELECT uuid FROM sucursales WHERE id=1").fetchone()
    user_uuid = conn.execute("SELECT uuid, sucursal_uuid FROM usuarios WHERE id=1").fetchone()
    role_uuid = conn.execute("SELECT uuid FROM roles WHERE id=1").fetchone()
    hh_columns = {row[1] for row in conn.execute("PRAGMA table_info(happy_hour_rules)").fetchall()}

    assert loyalty["nombre_programa"] == "Programa de Puntos"
    assert toggle["activo"] == 1
    assert tax["valor"] == "16.0"
    assert branch_uuid["uuid"]
    assert user_uuid["uuid"]
    assert user_uuid["sucursal_uuid"] == branch_uuid["uuid"]
    assert role_uuid["uuid"]
    assert {"uuid", "sucursal_uuid"}.issubset(hh_columns)


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


def test_configuracion_happy_hour_ui_uses_product_search_instead_of_product_id_text_capture() -> None:
    content = CONFIG_UI.read_text(encoding="utf-8")

    assert 'combo_scope.addItem("Producto", "producto_id")' in content
    assert 'combo_scope.addItem("Producto ID", "producto_id")' not in content
    assert "ProductSearchBox" in content
    assert "Selecciona un producto válido para la regla." in content
    assert 'scope_value = str(selected_product_option.id)' in content


def test_configuracion_entity_selectors_use_search_boxes_instead_of_mass_loaded_combos() -> None:
    content = CONFIG_UI.read_text(encoding="utf-8")

    required_fragments = [
        "BranchSearchBox",
        "EmployeeSearchBox",
        "self.branch_install_selector = BranchSearchBox(",
        "branch_selector = BranchSearchBox(",
        "employee_selector = EmployeeSearchBox(",
        "selected_branch_option.id if selected_branch_option is not None else \"\"",
        "self._selected_install_branch_option.id if self._selected_install_branch_option is not None else \"\"",
    ]
    for fragment in required_fragments:
        assert fragment in content

    forbidden_fragments = [
        "self.cmb_sucursal_inst = QComboBox()",
        "combo_branch = QComboBox()",
        "cmb_sucursal = QComboBox()",
        'cmb_empleado = QComboBox(); cmb_empleado.addItem("(ninguno)", None)',
        "self._enable_combo_search(",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in content


def test_config_repository_owns_remaining_configuration_sql_boundaries() -> None:
    content = CONFIG_REPOSITORY.read_text(encoding="utf-8")

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


def test_config_repository_removed_unused_legacy_branch_identity_helpers_and_lastrowid() -> None:
    content = CONFIG_REPOSITORY.read_text(encoding="utf-8")

    assert "def create_branch" not in content
    assert "def update_branch" not in content
    assert "def disable_branch" not in content
    assert "lastrowid" not in content


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
        payload={"role_name": "gerente"},
    )

    event = publisher.published_events[0]
    assert event["branch_id"][14] == "7"
    assert event["branch_id"] == event["branch_id"].lower()


def test_permission_event_publisher_does_not_default_branch_identity_to_integer_one() -> None:
    content = CONFIG_SERVICE.read_text(encoding="utf-8")

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


def test_configuracion_identity_contracts_expose_uuid_instead_of_int_types() -> None:
    content = CONFIG_SERVICE.read_text(encoding="utf-8")

    forbidden_patterns = [
        "def get_branch(self, branch_id: int)",
        "branch_id: int | None",
        "user_id: int | None",
        "role_id: int | None",
        "def get_user_form_data(self, user_id: int)",
        "def role_permissions(self, role_id: int)",
    ]
    for pattern in forbidden_patterns:
        assert pattern not in content


def test_config_repository_can_resolve_uuid_identities_for_configuration_entities() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE sucursales(id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, nombre TEXT, activa INTEGER);
        CREATE TABLE roles(id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, nombre TEXT, descripcion TEXT);
        CREATE TABLE usuarios(id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, usuario TEXT, nombre TEXT, email TEXT, rol TEXT, sucursal_uuid TEXT, activo INTEGER DEFAULT 1, empleado_id INTEGER, password_hash TEXT);
        CREATE TABLE rol_permisos(rol_uuid TEXT, modulo TEXT, accion TEXT, permitido INTEGER);
        INSERT INTO sucursales(uuid, nombre, activa) VALUES('019b17a7-0000-7000-8000-000000000101', 'Principal', 1);
        INSERT INTO roles(uuid, nombre, descripcion) VALUES('019b17a7-0000-7000-8000-000000000102', 'gerente', 'Gerente');
        INSERT INTO usuarios(uuid, usuario, nombre, email, rol, sucursal_uuid, activo) VALUES('019b17a7-0000-7000-8000-000000000103', 'ana', 'Ana', 'ana@example.com', 'gerente', '019b17a7-0000-7000-8000-000000000101', 1);
        """
    )
    repository = ConfigRepository(conn)

    assert repository.get_branch("019b17a7-0000-7000-8000-000000000101")["nombre"] == "Principal"
    assert repository.role_name_for_id("019b17a7-0000-7000-8000-000000000102") == "gerente"
    assert repository.username_for_uuid("019b17a7-0000-7000-8000-000000000103") == "ana"


def test_config_repository_rejects_numeric_legacy_identity_inputs() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE sucursales(id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, nombre TEXT, activa INTEGER);
        CREATE TABLE roles(id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, nombre TEXT, descripcion TEXT);
        CREATE TABLE usuarios(id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, usuario TEXT, nombre TEXT, email TEXT, rol TEXT, sucursal_uuid TEXT, activo INTEGER DEFAULT 1, empleado_id INTEGER, password_hash TEXT);
        CREATE TABLE rol_permisos(rol_uuid TEXT, modulo TEXT, accion TEXT, permitido INTEGER);
        INSERT INTO sucursales(uuid, nombre, activa) VALUES('019b17a7-0000-7000-8000-000000000111', 'Principal', 1);
        INSERT INTO roles(uuid, nombre, descripcion) VALUES('019b17a7-0000-7000-8000-000000000112', 'gerente', 'Gerente');
        INSERT INTO usuarios(uuid, usuario, nombre, email, rol, sucursal_uuid, activo) VALUES('019b17a7-0000-7000-8000-000000000113', 'ana', 'Ana', 'ana@example.com', 'gerente', '019b17a7-0000-7000-8000-000000000111', 1);
        """
    )
    repository = ConfigRepository(conn)

    checks = [
        (repository.get_branch, ("1",), "sucursales.id"),
        (repository.get_user_form_data, ("1",), "usuarios.id"),
        (repository.role_permissions, ("1",), "role_id"),
    ]
    for func, args, expected_field in checks:
        try:
            func(*args)
        except ValueError as exc:
            assert expected_field in str(exc) or "UUIDv7" in str(exc)
        else:
            raise AssertionError(f"{func.__name__} must reject numeric legacy identities")


def test_config_repository_requires_uuid_configuration_schema_for_canonical_runtime() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE sucursales(id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, activa INTEGER);
        CREATE TABLE usuarios(id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT, nombre TEXT, email TEXT, rol TEXT, sucursal_id INTEGER, activo INTEGER DEFAULT 1, empleado_id INTEGER, password_hash TEXT);
        CREATE TABLE roles(id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, descripcion TEXT);
        CREATE TABLE rol_permisos(rol_id INTEGER, modulo TEXT, accion TEXT, permitido INTEGER);
        """
    )
    repository = ConfigRepository(conn)

    for func, args in (
        (repository.get_all_branches, ()),
        (repository.list_users_v13, ()),
        (repository.save_role_permissions, ("019b17a7-0000-7000-8000-000000000121", {})),
    ):
        try:
            func(*args)
        except RuntimeError as exc:
            assert "requires" in str(exc)
        else:
            raise AssertionError(f"{func.__name__} must require migrated UUID schema")


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


def test_configuracion_save_user_event_uses_persisted_uuid_identity() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE usuarios(id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, usuario TEXT, nombre TEXT, email TEXT, rol TEXT, sucursal_uuid TEXT, activo INTEGER DEFAULT 1, empleado_id INTEGER, password_hash TEXT);
        CREATE TABLE sucursales(id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT, nombre TEXT, activa INTEGER DEFAULT 1);
        INSERT INTO sucursales(uuid, nombre, activa) VALUES('019b17a7-0000-7000-8000-000000000201', 'Principal', 1);
        """
    )
    repository = ConfigRepository(conn)
    from core.services.configuration_settings_service import UserManagementService

    publisher = PermissionEventPublisher()
    service = UserManagementService(repository, publisher)
    user_id = service.save_user(
        user_id=None,
        username="ana",
        name="Ana",
        email="ana@example.com",
        role="admin",
        branch_id="019b17a7-0000-7000-8000-000000000201",
        active=True,
        employee_id=None,
        password_hash="hash",
        operation_id=new_uuid(),
        actor="admin",
    )

    event = publisher.published_events[0]
    assert event["entity_id"] == user_id
    assert event["entity_id"][14] == "7"
