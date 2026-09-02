import sqlite3
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "pos_spj_v13.4"))

from backend.shared.ids import new_uuid  # noqa: E402
from core.services.configuration_settings_service import (  # noqa: E402
    ModuleAccessService,
    PermissionEventPublisher,
    PermissionQueryService,
    RoleManagementService,
)
from repositories.config_repository import ConfigRepository  # noqa: E402


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # Born-clean schema: id columns ARE the UUIDv7 identity directly — mirrors
    # migrations/m000_base_schema.py, the real, current shape `ConfigRepository`
    # already reads/writes against (`_require_uuid_column()` always returns
    # "id", no separate uuid column exists anywhere). The previous hand-rolled
    # `INTEGER PRIMARY KEY AUTOINCREMENT` + `uuid TEXT` layout predates that
    # cutover and made every mutation here raise `sqlite3.IntegrityError:
    # datatype mismatch` (a UUID string can't be coerced into a rowid-alias
    # INTEGER column).
    conn.executescript(
        """
        CREATE TABLE roles(id TEXT PRIMARY KEY, nombre TEXT UNIQUE, descripcion TEXT, activo INTEGER DEFAULT 1);
        CREATE TABLE usuarios(id TEXT PRIMARY KEY, usuario TEXT, nombre TEXT, rol TEXT, sucursal_id TEXT, activo INTEGER DEFAULT 1);
        CREATE TABLE sucursales(id TEXT PRIMARY KEY, nombre TEXT, activa INTEGER DEFAULT 1);
        CREATE TABLE rol_permisos(id TEXT PRIMARY KEY, rol_id TEXT, modulo TEXT, accion TEXT, permitido INTEGER);
        CREATE TABLE audit_logs(id TEXT PRIMARY KEY, fecha TEXT, usuario TEXT, modulo TEXT, accion TEXT, detalles TEXT);
        INSERT INTO sucursales(id, nombre, activa) VALUES('019b17a7-0000-7000-8000-000000000301', 'Principal', 1);
        INSERT INTO roles(id, nombre, descripcion) VALUES('019b17a7-0000-7000-8000-000000000302', 'admin', 'Administrador');
        INSERT INTO rol_permisos(id, rol_id, modulo, accion, permitido) VALUES('019b17a7-0000-7000-8000-000000000401', '019b17a7-0000-7000-8000-000000000302', 'CONFIGURACION', 'ver', 1);
        INSERT INTO rol_permisos(id, rol_id, modulo, accion, permitido) VALUES('019b17a7-0000-7000-8000-000000000402', '019b17a7-0000-7000-8000-000000000302', 'CONFIGURACION', 'editar', 1);
        """
    )
    return conn


def test_roles_permissions_canonical_flow_emits_events_and_queries_access() -> None:
    repository = ConfigRepository(_connection())
    publisher = PermissionEventPublisher()
    role_service = RoleManagementService(repository, publisher)
    permission_query = PermissionQueryService(repository)
    module_access = ModuleAccessService(repository, publisher)

    role_id = role_service.save_role(
        role_id=None,
        name="gerente_config",
        description="Gerente de configuración",
        operation_id=new_uuid(),
        actor="admin",
    )
    role_service.save_role(
        role_id=role_id,
        name="gerente_config",
        description="Gerente actualizado",
        operation_id=new_uuid(),
        actor="admin",
    )

    matrix = dict(permission_query.permission_matrix())
    assert "ver" in matrix["POS"]
    assert "ver" in matrix["CAJA"]
    assert "ver" in matrix["CONFIG_SEGURIDAD"]
    assert "editar" in matrix["CONFIGURACION"]

    module_access._cache[role_id] = {("CONFIG_SEGURIDAD", "editar"): False}
    permissions = {("CONFIG_SEGURIDAD", "ver"): True, ("CONFIG_SEGURIDAD", "editar"): True}
    module_access.save_role_permissions(
        role_id,
        permissions,
        operation_id=new_uuid(),
        actor="admin",
    )

    saved = permission_query.role_permissions(role_id)
    assert saved[("CONFIG_SEGURIDAD", "ver")] is True
    assert saved[("CONFIG_SEGURIDAD", "editar")] is True
    assert module_access.has_permission(role_id, "CONFIG_SEGURIDAD", "editar") is True
    assert module_access._cache[role_id][("CONFIG_SEGURIDAD", "editar")] is True

    module_path = REPO_ROOT / "pos_spj_v13.4" / "modulos" / "configuracion.py"
    assert "get_legacy_users" not in module_path.read_text(encoding="utf-8")

    event_names = [event["event_name"] for event in publisher.published_events]
    assert "ROLE_PERMISSIONS_UPDATED" in event_names
    assert "MODULE_ACCESS_UPDATED" in event_names
    assert all(event["operation_id"] for event in publisher.published_events)
    assert all(event["operation_id"][14] == "7" for event in publisher.published_events)
    assert all(event["entity_id"][14] == "7" for event in publisher.published_events)
    assert all(event["entity_id"] == role_id for event in publisher.published_events if event["event_name"] in {"ROLE_PERMISSIONS_UPDATED", "MODULE_ACCESS_UPDATED"})
