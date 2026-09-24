"""Búsqueda de sucursales acotada al usuario — contra el esquema REAL.

La regla que se fija aquí es de seguridad, no de comodidad: un cajero no debe
poder DESCUBRIR por búsqueda sucursales fuera de su alcance sólo porque conozca
el nombre. El orden correcto es `usuario → permitidas → consulta → resultados`;
filtrar en el frontend sería una fuga.

Misma convención que `test_permission_query_service.py`: cadena de migraciones
completa, sin dobles. Un doble no probaría nada, porque lo que puede fallar es
justo la correspondencia entre el SQL y las tablas reales.
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.application.security.branch_scope_query_service import (
    BranchScopeQueryService,
    BranchSearchQuery,
)
from backend.shared.ids import new_uuid


@pytest.fixture(scope="module")
def migrated_db(tmp_path_factory):
    from migrations.engine import up

    path = tmp_path_factory.mktemp("sucursales") / "erp.db"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    up(conn)
    yield conn
    conn.close()


@pytest.fixture
def conn(migrated_db):
    yield migrated_db
    migrated_db.rollback()


def _sucursal(conn, nombre: str, *, activa: int = 1) -> str:
    branch_id = new_uuid()
    conn.execute("INSERT INTO sucursales (id, nombre, activa) VALUES (?,?,?)",
                 (branch_id, nombre, activa))
    return branch_id


def _usuario(conn, rol: str, branch_id: str) -> str:
    user_id = new_uuid()
    conn.execute(
        "INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, sucursal_id,"
        " activo) VALUES (?,?,?,?,?,?,1)",
        (user_id, rol, f"u_{user_id[:8]}", "x", rol, branch_id))
    return user_id


def _servicio(conn, permiso=None):
    return BranchScopeQueryService(conn, global_scope_permission=permiso)


# ── la regla de seguridad ───────────────────────────────────────────────────
def test_un_cajero_no_descubre_una_sucursal_ajena_por_su_nombre(conn):
    """El caso que motivó todo esto."""
    propia = _sucursal(conn, "San Bartolo")
    _sucursal(conn, "Corregidora")
    cajero = _usuario(conn, "cajero", propia)

    encontradas = _servicio(conn).search(
        BranchSearchQuery(text="Corregidora", allowed_for_user=cajero))

    assert encontradas == []


def test_el_cajero_si_encuentra_la_suya(conn):
    propia = _sucursal(conn, "San Bartolo")
    cajero = _usuario(conn, "cajero", propia)

    encontradas = _servicio(conn).search(
        BranchSearchQuery(text="bartolo", allowed_for_user=cajero))

    assert [b.branch_id for b in encontradas] == [propia]


def test_sin_usuario_no_hay_resultados(conn):
    """`allowed_for_user=None` NO significa 'todas': significa que no hay
    identidad contra la que resolver, y eso falla cerrado."""
    _sucursal(conn, "San Bartolo")
    assert _servicio(conn).search(BranchSearchQuery(text="bartolo")) == []


def test_un_usuario_desconocido_no_hereda_alcance(conn):
    _sucursal(conn, "San Bartolo")
    assert _servicio(conn).search(
        BranchSearchQuery(allowed_for_user=new_uuid())) == []


# ── resolución del alcance ──────────────────────────────────────────────────
def test_la_asignacion_gana_sobre_la_sucursal_propia(conn):
    propia = _sucursal(conn, "Propia")
    asignada = _sucursal(conn, "Asignada")
    usuario = _usuario(conn, "cajero", propia)
    conn.execute(
        "INSERT INTO usuarios_sucursales (usuario_id, sucursal_id) VALUES (?,?)",
        (usuario, asignada))

    permitidas = _servicio(conn).allowed_branch_ids(usuario)

    assert set(permitidas) == {asignada}


def test_sin_asignaciones_se_usa_la_sucursal_propia(conn):
    """El respaldo NO es adorno: `usuarios_sucursales` está vacía en la
    instalación real y sin esto el alcance sería vacío para todo el mundo."""
    propia = _sucursal(conn, "Propia")
    usuario = _usuario(conn, "cajero", propia)

    assert _servicio(conn).allowed_branch_ids(usuario) == (propia,)


def test_el_permiso_global_abre_todas(conn):
    propia = _sucursal(conn, "Propia")
    _sucursal(conn, "Otra")
    usuario = _usuario(conn, "cajero", propia)
    rol_id = conn.execute(
        "SELECT id FROM roles WHERE lower(trim(nombre))='cajero'").fetchone()["id"]
    conn.execute(
        "INSERT INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
        " VALUES (?,?,?,?,1)",
        (new_uuid(), rol_id, "INVENTARIO", "ver.todas_sucursales"))

    servicio = _servicio(conn, "INVENTARIO.ver.todas_sucursales")

    assert servicio.allowed_branch_ids(usuario) is None
    assert len(servicio.search(BranchSearchQuery(allowed_for_user=usuario))) >= 2


def test_el_administrador_entra_por_el_comodin(conn):
    """Sus permisos llegan como `{"*"}` SIN expandir. Comparar por pertenencia
    literal es lo que hacía `InventoryScopePolicy`, y por eso denegaba a los
    administradores."""
    propia = _sucursal(conn, "Propia")
    _sucursal(conn, "Otra")
    admin = _usuario(conn, "admin", propia)

    servicio = _servicio(conn, "INVENTARIO.ver.todas_sucursales")

    assert servicio.allowed_branch_ids(admin) is None


def test_sin_permiso_inyectado_no_hay_escape_global(conn):
    """Fallar cerrado: un servicio construido sin código de escape nunca
    concede alcance global, ni siquiera al administrador."""
    propia = _sucursal(conn, "Propia")
    _sucursal(conn, "Otra")
    admin = _usuario(conn, "admin", propia)

    assert _servicio(conn).allowed_branch_ids(admin) == (propia,)


# ── degradación y diagnóstico ───────────────────────────────────────────────
def test_buscar_por_codigo_no_revienta_y_no_inventa_resultados(conn):
    """`sucursales` no tiene columna `codigo`. Se degrada filtrando a CERO, no
    ignorando el criterio: ignorarlo devolvería filas que nadie pidió."""
    propia = _sucursal(conn, "San Bartolo")
    cajero = _usuario(conn, "cajero", propia)
    servicio = _servicio(conn)

    assert servicio.search(BranchSearchQuery(code="SB1", allowed_for_user=cajero)) == []
    razon = servicio.explain_empty(
        BranchSearchQuery(code="SB1", allowed_for_user=cajero))
    assert razon is not None and razon.code == "SIN_CODIGO"


def test_explica_que_no_hay_alcance(conn):
    """"Sin acceso" y "no existe" no pueden verse igual."""
    usuario = _usuario(conn, "cajero", "")

    razon = _servicio(conn).explain_empty(BranchSearchQuery(allowed_for_user=usuario))

    assert razon is not None and razon.code == "SIN_ALCANCE"


def test_explica_que_el_texto_no_coincide(conn):
    propia = _sucursal(conn, "San Bartolo")
    cajero = _usuario(conn, "cajero", propia)

    razon = _servicio(conn).explain_empty(
        BranchSearchQuery(text="zzzz", allowed_for_user=cajero))

    assert razon is not None and razon.code == "NO_COINCIDE"


def test_explica_que_las_sucursales_estan_inactivas(conn):
    propia = _sucursal(conn, "Inactiva", activa=0)
    cajero = _usuario(conn, "cajero", propia)

    razon = _servicio(conn).explain_empty(BranchSearchQuery(allowed_for_user=cajero))

    assert razon is not None and razon.code == "SIN_ACTIVAS"


def test_la_paginacion_acota(conn):
    propia = _sucursal(conn, "AAA")
    otra = _sucursal(conn, "BBB")
    usuario = _usuario(conn, "cajero", propia)
    for destino in (propia, otra):
        conn.execute(
            "INSERT INTO usuarios_sucursales (usuario_id, sucursal_id) VALUES (?,?)",
            (usuario, destino))
    servicio = _servicio(conn)

    primera = servicio.search(
        BranchSearchQuery(allowed_for_user=usuario, page=1, page_size=1))
    segunda = servicio.search(
        BranchSearchQuery(allowed_for_user=usuario, page=2, page_size=1))

    assert len(primera) == 1 and len(segunda) == 1
    assert primera[0].branch_id != segunda[0].branch_id
