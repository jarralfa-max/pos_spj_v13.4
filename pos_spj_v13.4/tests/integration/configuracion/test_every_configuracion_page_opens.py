"""Las 11 páginas de Configuración se abren contra una base real.

POR QUÉ ESTE ARCHIVO EXISTE
----------------------------
Usuarios y Roles reventó DOS VECES seguidas por el mismo motivo, en dos sitios
distintos del mismo archivo:

    AttributeError: 'sqlite3.Row' object has no attribute 'id'

La primera vez fue `list_users()/list_roles()`, que prometían DTOs y devolvían
filas. Se arregló ahí. Pero `_page_usuarios_roles` NO llamaba a ese
`list_users()`: iba directo al servicio de aplicación, así que se saltaba el
mapeo y recibía filas crudas otra vez. Arreglar un camino dejó el otro igual.

La lección no es "revisar mejor": es que arreglar el contrato de un método no
dice nada sobre quién lo llama. Lo único que cubre esa clase entera de fallo es
recorrer LAS ONCE páginas por la vía que usa el shell y mirar lo que sale.

Todas van por el mismo `page()`, así que una prueba parametrizada las cubre —y
cubre también las que se añadan después, porque la lista sale del registro, no
de aquí.
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.application.queries.configuracion.workspace_query_service import (
    ConfigPageViewModel,
    ConfigRowViewModel,
    ConfiguracionWorkspaceQueryService,
)
from backend.shared.ids import new_uuid

PAGE_IDS = sorted(ConfiguracionWorkspaceQueryService._HANDLERS)


@pytest.fixture
def conn():
    import migrations.m000_base_schema as base
    from migrations import engine as migrator

    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    base.up(c)
    c.commit()
    migrator.up(c)
    c.commit()
    yield c
    c.close()


def _servicio(conn):
    return ConfiguracionWorkspaceQueryService(conn)


# ── el recorrido completo ───────────────────────────────────────────────────
@pytest.mark.parametrize("page_id", PAGE_IDS)
def test_the_page_opens_on_a_fresh_install(conn, page_id):
    """Instalación recién migrada, sin que nadie haya creado nada.

    Es el estado en el que reventaba Usuarios y Roles: las migraciones siembran
    7 roles de sistema, así que la pantalla tenía filas que mapear desde el
    primer arranque.
    """
    modelo = _servicio(conn).page(page_id=page_id, search="")

    assert isinstance(modelo, ConfigPageViewModel)
    assert modelo.columns, f"{page_id} no declara columnas"
    for fila in modelo.rows:
        assert isinstance(fila, ConfigRowViewModel), (
            f"{page_id} devuelve {type(fila).__name__} en vez de ConfigRowViewModel")
        assert len(fila.cells) == len(modelo.columns), (
            f"{page_id}: {len(fila.cells)} celdas para {len(modelo.columns)} columnas")


@pytest.mark.parametrize("page_id", PAGE_IDS)
def test_the_page_survives_a_search_that_matches_nothing(conn, page_id):
    """El filtro corre sobre las celdas ya construidas: si una celda no es
    texto, filtrar revienta aunque abrir la página funcione."""
    modelo = _servicio(conn).page(page_id=page_id, search="zzz-no-existe-zzz")

    assert modelo.rows == ()
    assert modelo.empty_message


# ── la página que reventó, con datos ────────────────────────────────────────
def test_usuarios_roles_lists_a_real_user(conn):
    """El acceso exacto de la traza: `u.id` sobre lo que devuelve el servicio.

    Con la base vacía de usuarios esta página devolvía cero filas y no llegaba
    a tocar `u.id`, así que hace falta un usuario para reproducirlo.
    """
    user_id = new_uuid()
    conn.execute(
        "INSERT INTO usuarios (id, usuario, nombre, password_hash, rol, activo)"
        " VALUES (?,?,?,'x','Cajero',1)", (user_id, "ana", "Ana Ruiz"))
    conn.commit()

    modelo = _servicio(conn).page(page_id="config_usuarios_roles", search="")

    fila = next(f for f in modelo.rows if f.entity_id == user_id)
    assert fila.cells[0] == "ana"
    assert fila.cells[1] == "Ana Ruiz"
    assert fila.cells[4] == "Activo"
    assert fila.cells[5] == "Sin bloqueos"


def test_usuarios_roles_reports_a_locked_user(conn):
    """La columna Seguridad es el único sitio donde se ve un bloqueo; si el
    mapeo falla, un usuario bloqueado se lee como uno normal."""
    user_id = new_uuid()
    conn.execute(
        "INSERT INTO usuarios (id, usuario, nombre, password_hash, rol, activo,"
        " intentos_fallidos, bloqueado_hasta)"
        " VALUES (?,?,?,'x','Cajero',1,5,'2026-09-12 10:00:00')",
        (user_id, "beto", "Beto Lara"))
    conn.commit()

    modelo = _servicio(conn).page(page_id="config_usuarios_roles", search="")

    fila = next(f for f in modelo.rows if f.entity_id == user_id)
    assert "Bloqueado hasta" in fila.cells[5]


# ── el registro y el menú no pueden separarse ───────────────────────────────
def test_every_sidebar_entry_has_a_handler():
    """Una entrada en el menú sin handler es un `KeyError` al hacer clic —el
    mismo tipo de fallo que esto persigue, sólo que una capa más arriba."""
    from frontend.desktop.modules.configuracion.configuracion_routes import (
        CONFIGURACION_ROUTE_IDS,
    )

    sin_handler = sorted(CONFIGURACION_ROUTE_IDS - set(PAGE_IDS))
    assert not sin_handler, (
        f"Rutas en el menú lateral sin handler en el servicio: {sin_handler}")
