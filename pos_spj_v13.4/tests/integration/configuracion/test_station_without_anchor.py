"""SDLC-ARQ-TERM-002 · sin ancla no hay sesión operativa ni fallback silencioso.

Antes, sin `sucursal_instalacion_id`, `ApplicationContextBuilder` tomaba la
sucursal propia del usuario: la estación cambiaba de sucursal al iniciar sesión.
"""
from __future__ import annotations

import pytest

from backend.bootstrap.application_context_builder import ApplicationContextBuilder
from backend.bootstrap.application_context_errors import (
    SiteAccessDeniedError,
    StationNotAnchoredError,
)
from backend.bootstrap.permission_evaluator import PermissionEvaluator
from backend.shared.ids import new_uuid
from tests.integration.configuracion import _reanchor_support as s


@pytest.fixture(scope="module")
def template():
    conn = s.build_template()
    yield conn
    conn.close()


@pytest.fixture
def conn(template):
    copia = s.copy_of(template)
    yield copia
    copia.close()


def _rol_con(conn, nombre: str, *codigos: str) -> None:
    rol_id = new_uuid()
    conn.execute("INSERT INTO roles (id, nombre) VALUES (?, ?)", (rol_id, nombre))
    for codigo in codigos:
        modulo, accion = codigo.split(".", 1)
        conn.execute("INSERT INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
                     " VALUES (?,?,?,?,1)", (new_uuid(), rol_id, modulo, accion))
    conn.commit()


def test_with_an_anchor_the_session_operates_the_anchored_site(conn):
    propia = s.sucursal(conn, "Propia")
    cajero = s.usuario(conn, "cajero", s.ancla(conn))
    ctx = ApplicationContextBuilder(conn).build(s.login(cajero, "cajero", propia))
    assert ctx.branch_id == s.ancla(conn)


def test_a_user_who_cannot_re_anchor_gets_no_session(conn):
    propia = s.sucursal(conn, "Propia")
    s.quitar_ancla(conn)
    cajero = s.usuario(conn, "cajero", propia)
    with pytest.raises(StationNotAnchoredError, match="no tiene una sucursal anclada"):
        ApplicationContextBuilder(conn).build(s.login(cajero, "cajero", propia))


def test_the_login_flow_treats_it_as_a_site_denial(conn):
    """El coordinador ya revoca la sesión y muestra el motivo ante esta familia."""
    assert issubclass(StationNotAnchoredError, SiteAccessDeniedError)


def test_the_owner_gets_a_repair_session_without_branch_or_operations(conn):
    propia = s.sucursal(conn, "Propia")
    s.quitar_ancla(conn)
    dueno = s.usuario(conn, "system_owner", propia)
    ctx = ApplicationContextBuilder(conn).build(s.login(dueno, "system_owner", propia))
    assert ctx.branch_id == "" and ctx.branch_name == ""
    for modulo in ("sales_pos", "cash_register", "inventory", "transfers", "purchasing",
                   "finance", "orders_delivery"):
        assert not ctx.site_allows_module(modulo), modulo
    assert ctx.site_allows_module("configuracion")
    assert PermissionEvaluator(ctx).has_permission("CONFIGURACION.estacion.reanclar")


def test_a_granted_non_admin_role_also_gets_the_repair_session(conn):
    _rol_con(conn, "soporte", "CONFIGURACION.estacion.reanclar", "CONFIGURACION.ver")
    propia = s.sucursal(conn, "Propia")
    s.quitar_ancla(conn)
    tecnico = s.usuario(conn, "soporte", propia)
    ctx = ApplicationContextBuilder(conn).build(s.login(tecnico, "soporte", propia))
    assert ctx.branch_id == "" and not ctx.site_allows_module("sales_pos")


def test_an_anchor_pointing_to_a_vanished_branch_counts_as_no_anchor(conn):
    propia = s.sucursal(conn, "Propia")
    conn.execute("UPDATE configuraciones SET valor=? WHERE clave='sucursal_instalacion_id'",
                 (new_uuid(),))
    conn.commit()
    cajero = s.usuario(conn, "cajero", propia)
    with pytest.raises(StationNotAnchoredError):
        ApplicationContextBuilder(conn).build(s.login(cajero, "cajero", propia))
