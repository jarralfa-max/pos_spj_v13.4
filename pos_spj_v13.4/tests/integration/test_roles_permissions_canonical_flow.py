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
    conn.executescript(
        """
        CREATE TABLE roles(id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT UNIQUE, descripcion TEXT);
        CREATE TABLE usuarios(id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT, nombre TEXT, rol TEXT, sucursal_id INTEGER, activo INTEGER DEFAULT 1);
        CREATE TABLE sucursales(id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, activa INTEGER DEFAULT 1);
        CREATE TABLE rol_permisos(rol_id INTEGER, modulo TEXT, accion TEXT, permitido INTEGER);
        CREATE TABLE audit_logs(fecha TEXT, usuario TEXT, modulo TEXT, accion TEXT, detalles TEXT);
        INSERT INTO sucursales(nombre, activa) VALUES('Principal', 1);
        INSERT INTO rol_permisos(rol_id, modulo, accion, permitido) VALUES(1, 'CONFIGURACION', 'ver', 1);
        INSERT INTO rol_permisos(rol_id, modulo, accion, permitido) VALUES(1, 'CONFIGURACION', 'editar', 1);
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
    assert all("role_id" not in event["payload"] for event in publisher.published_events)
