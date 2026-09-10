"""`PermissionQueryService` contra el esquema y los roles REALES.

No usa dobles: monta la base con la cadena de migraciones completa y consulta
los roles de sistema que siembra `m000_base_schema._seed_system_roles()`. Un
doble aquí no probaría nada, porque lo que puede fallar es justamente la
correspondencia entre el SQL y las tablas.

Lo que se fija:
  - los conteos por rol coinciden con lo que el sembrado concede,
  - `permitido=0` REVOCA de verdad (el error clásico es tratar las excepciones
    como una unión, y entonces una revocación no hace nada),
  - una excepción de sucursal sólo aplica en ESA sucursal,
  - un usuario que no se puede resolver no hereda permisos de nadie.
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.application.security.permission_query_service import PermissionQueryService
from backend.infrastructure.db.repositories.security.permission_repository import (
    SqlitePermissionRepository,
)
from backend.shared.ids import new_uuid


@pytest.fixture(scope="module")
def migrated_db(tmp_path_factory):
    from migrations.engine import up

    path = tmp_path_factory.mktemp("permisos") / "erp.db"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    up(conn)
    yield conn
    conn.close()


@pytest.fixture
def conn(migrated_db):
    """Cada test parte del mismo estado: se deshace lo que escriba."""
    yield migrated_db
    migrated_db.rollback()


@pytest.fixture
def service(conn):
    return PermissionQueryService(SqlitePermissionRepository(conn))


@pytest.fixture
def branch_id(conn):
    return conn.execute("SELECT id FROM sucursales LIMIT 1").fetchone()["id"]


def _create_user(conn, role: str, branch_id: str) -> str:
    user_id = new_uuid()
    conn.execute(
        "INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, sucursal_id, activo)"
        " VALUES (?,?,?,?,?,?,1)",
        (user_id, role, f"usuario_{user_id[:8]}", "x", role, branch_id),
    )
    return user_id


# ── lo que concede cada rol sembrado ────────────────────────────────────────
@pytest.mark.parametrize(
    "role, expected_count",
    [
        # cajero: DASHBOARD.ver + POS(ver,crear,editar) + CAJA(ver,crear)
        #       + CLIENTES(ver,crear) + COTIZACIONES(ver,crear)
        #       + INVENTARIO.ver + PRODUCTOS.ver
        ("cajero", 12),
        # repartidor: sólo DELIVERY ver/editar
        ("repartidor", 2),
        # solo_lectura: `ver` en los 19 módulos sembrados
        ("solo_lectura", 19),
    ],
)
def test_seeded_roles_resolve_the_permissions_the_seed_grants(
    service, conn, branch_id, role, expected_count,
):
    user_id = _create_user(conn, role, branch_id)
    assert len(service.permission_codes_for_user(user_id, branch_id)) == expected_count


def test_codes_come_back_in_comparison_form(service, conn, branch_id):
    """MAYÚSCULAS. Si esto cambiara, `PermissionEvaluator` denegaría todo."""
    user_id = _create_user(conn, "cajero", branch_id)
    codes = service.permission_codes_for_user(user_id, branch_id)
    assert "POS.VER" in codes
    assert "POS.ver" not in codes
    assert all(code == code.upper() for code in codes)


def test_admin_gets_the_global_wildcard_not_an_expanded_catalog(service, conn, branch_id):
    """Un permiso creado DESPUÉS del login también debe valer para el admin."""
    user_id = _create_user(conn, "admin", branch_id)
    assert service.permission_codes_for_user(user_id, branch_id) == frozenset({"*"})


# ── excepciones ─────────────────────────────────────────────────────────────
def test_user_override_revokes_a_permission_the_role_grants(service, conn, branch_id):
    user_id = _create_user(conn, "cajero", branch_id)
    assert "POS.VER" in service.permission_codes_for_user(user_id, branch_id)

    conn.execute(
        "INSERT INTO usuario_permisos (id, usuario_id, modulo, accion, permitido)"
        " VALUES (?,?,?,?,0)",
        (new_uuid(), user_id, "POS", "ver"),
    )
    assert "POS.VER" not in service.permission_codes_for_user(user_id, branch_id)


def test_user_override_grants_a_permission_the_role_does_not(service, conn, branch_id):
    user_id = _create_user(conn, "cajero", branch_id)
    assert "COMPRAS.CREAR" not in service.permission_codes_for_user(user_id, branch_id)

    conn.execute(
        "INSERT INTO usuario_permisos (id, usuario_id, modulo, accion, permitido)"
        " VALUES (?,?,?,?,1)",
        (new_uuid(), user_id, "COMPRAS", "crear"),
    )
    assert "COMPRAS.CREAR" in service.permission_codes_for_user(user_id, branch_id)


def test_branch_override_applies_only_inside_that_branch(service, conn, branch_id):
    user_id = _create_user(conn, "cajero", branch_id)
    conn.execute(
        "INSERT INTO usuario_sucursal_permisos"
        " (id, usuario_id, sucursal_id, modulo, accion, permitido) VALUES (?,?,?,?,?,1)",
        (new_uuid(), user_id, branch_id, "COMPRAS", "crear"),
    )

    assert "COMPRAS.CREAR" in service.permission_codes_for_user(user_id, branch_id)
    otra_sucursal = new_uuid()
    assert "COMPRAS.CREAR" not in service.permission_codes_for_user(user_id, otra_sucursal)


def test_branch_override_beats_the_user_override(service, conn, branch_id):
    """Lo más específico gana: la sucursal se aplica después del usuario."""
    user_id = _create_user(conn, "cajero", branch_id)
    conn.execute(
        "INSERT INTO usuario_permisos (id, usuario_id, modulo, accion, permitido)"
        " VALUES (?,?,?,?,1)",
        (new_uuid(), user_id, "COMPRAS", "crear"),
    )
    conn.execute(
        "INSERT INTO usuario_sucursal_permisos"
        " (id, usuario_id, sucursal_id, modulo, accion, permitido) VALUES (?,?,?,?,?,0)",
        (new_uuid(), user_id, branch_id, "COMPRAS", "crear"),
    )
    assert "COMPRAS.CREAR" not in service.permission_codes_for_user(user_id, branch_id)


# ── fallar cerrado ──────────────────────────────────────────────────────────
def test_unknown_user_gets_nothing(service, branch_id):
    assert service.permission_codes_for_user(new_uuid(), branch_id) == frozenset()


def test_blank_user_id_gets_nothing(service, branch_id):
    assert service.permission_codes_for_user("", branch_id) == frozenset()


def test_user_with_an_unknown_role_gets_nothing(service, conn, branch_id):
    user_id = _create_user(conn, "rol_que_no_existe", branch_id)
    assert service.permission_codes_for_user(user_id, branch_id) == frozenset()
