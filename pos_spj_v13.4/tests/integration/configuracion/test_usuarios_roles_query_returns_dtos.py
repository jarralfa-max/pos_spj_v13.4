"""Usuarios y Roles: el servicio de consulta devuelve DTOs, no filas crudas.

EL FALLO QUE ESTO FIJA
-----------------------
`ConfiguracionWorkspaceQueryService.list_users/get_user_form_data/list_roles`
declaraban devolver `UserSettingsDTO`/`RoleSettingsDTO` —y el archivo ya
importaba los tres constructores— pero devolvían las FILAS del repositorio tal
cual. La página hace `r.id`, así que reventaba nada más abrirse:

    AttributeError: 'sqlite3.Row' object has no attribute 'id'

No al usarla: al CONSTRUIRLA. `_build_roles_card()` llama a `_reload_roles()`
desde el `__init__`, así que la pantalla de Usuarios y Roles no llegaba a
aparecer.

POR QUÉ NO LO CAZÓ NADA
------------------------
Las firmas prometían el DTO, así que leer el código daba la impresión correcta,
y ninguna prueba construía el servicio contra una base real para mirar lo que
sale. Estas van por ahí a propósito: con un doble del repositorio, una fila
falsa con atributos habría pasado igual que el DTO.
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.application.dto.configuracion_dtos import RoleSettingsDTO, UserSettingsDTO
from backend.application.queries.configuracion.workspace_query_service import (
    ConfiguracionWorkspaceQueryService,
)
from backend.shared.ids import new_uuid


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


def _rol(conn, nombre="Cajero", descripcion="Opera la caja"):
    rol_id = new_uuid()
    conn.execute("INSERT INTO roles (id, nombre, descripcion) VALUES (?,?,?)",
                 (rol_id, nombre, descripcion))
    conn.commit()
    return rol_id


def _usuario(conn, *, usuario="ana", nombre="Ana Ruiz", rol="Cajero", activo=1):
    user_id = new_uuid()
    conn.execute(
        "INSERT INTO usuarios (id, usuario, nombre, password_hash, rol, activo)"
        " VALUES (?,?,?,'x',?,?)", (user_id, usuario, nombre, rol, activo))
    conn.commit()
    return user_id


# ── roles ───────────────────────────────────────────────────────────────────
def test_the_roles_come_back_as_dtos_with_an_id_attribute(conn):
    """El acceso exacto que reventaba: `r.id` sobre lo que devuelve la consulta."""
    rol_id = _rol(conn)

    roles = _servicio(conn).list_roles()

    assert roles and all(isinstance(r, RoleSettingsDTO) for r in roles)
    # La base trae 7 roles de sistema sembrados por las migraciones, asi que se
    # busca el creado en vez de exigir que sea el unico.
    creado = next(r for r in roles if r.id == rol_id)
    assert creado.name == "Cajero"
    assert creado.description == "Opera la caja"


def test_the_role_counts_only_active_users(conn):
    """El número avisa de que un rol está EN USO antes de tocarlo; contar bajas
    lo haría parecer ocupado cuando no lo está."""
    rol_id = _rol(conn)
    _usuario(conn, usuario="ana", activo=1)
    _usuario(conn, usuario="beto", activo=0)

    # Se busca por id y no por `[0]`: el orden lo fija `ORDER BY nombre` junto a
    # los roles sembrados, asi que la posicion depende de como se llame el rol.
    rol = next(r for r in _servicio(conn).list_roles() if r.id == rol_id)
    assert rol.user_count == 1


def test_the_seeded_system_roles_are_already_dtos(conn):
    """Sin crear nada: las migraciones siembran 7 roles de sistema, y la
    pantalla los lee por la misma via. Si el mapeo faltara, Usuarios y Roles
    reventaria en una instalacion recien hecha, antes de que nadie cree nada."""
    roles = _servicio(conn).list_roles()
    assert len(roles) >= 7
    assert all(isinstance(r, RoleSettingsDTO) and r.id for r in roles)
    assert "admin" in {r.name for r in roles}


# ── usuarios ────────────────────────────────────────────────────────────────
def test_the_users_come_back_as_dtos(conn):
    """Mismo fallo esperando en la otra mitad de la pantalla."""
    _rol(conn)
    user_id = _usuario(conn)

    usuarios = _servicio(conn).list_users()

    assert usuarios and all(isinstance(u, UserSettingsDTO) for u in usuarios)
    assert {u.id for u in usuarios} == {user_id}
    assert usuarios[0].username == "ana"
    assert usuarios[0].name == "Ana Ruiz"
    assert usuarios[0].active is True


def test_the_user_form_data_comes_back_as_a_dto(conn):
    _rol(conn)
    user_id = _usuario(conn, usuario="ana", nombre="Ana Ruiz")

    dto = _servicio(conn).get_user_form_data(user_id)

    assert isinstance(dto, UserSettingsDTO)
    assert dto.id == user_id
    assert dto.username == "ana"


def test_an_unknown_user_gets_none_not_an_empty_dto(conn):
    """Un DTO vacío abriría el formulario en blanco, como si fuera un alta —y
    guardar crearía un usuario en vez de fallar."""
    assert _servicio(conn).get_user_form_data(new_uuid()) is None


# ── la propiedad derivada que la pantalla usa ───────────────────────────────
def test_a_locked_user_is_reported_as_locked(conn):
    """`UserSettingsDTO.locked` sólo existe en el DTO: sobre una fila cruda el
    bloqueo era invisible, aunque la columna estuviera poblada."""
    _rol(conn)
    user_id = _usuario(conn)
    conn.execute("UPDATE usuarios SET intentos_fallidos=5,"
                 " bloqueado_hasta=datetime('now','+15 minutes') WHERE id=?", (user_id,))
    conn.commit()

    usuario = next(u for u in _servicio(conn).list_users() if u.id == user_id)
    assert usuario.failed_attempts == 5
    assert usuario.locked is True


# ── la pantalla, entera ─────────────────────────────────────────────────────
def test_the_usuarios_roles_page_opens(conn):
    """La comprobación que habría cazado el fallo, y la que no existía.

    Las de arriba fijan el contrato del servicio; ésta construye la PANTALLA por
    la misma vía que el shell (`build_page`), que es donde reventaba. Un
    contrato correcto y una pantalla que no abre son cosas distintas: aquí la
    página llama a `_reload_roles()` desde su `__init__`, así que el fallo
    ocurría antes de que nadie pudiera interactuar con ella.
    """
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.configuracion.configuracion_presenter import (
        ConfiguracionPresenter,
    )
    from frontend.desktop.modules.configuracion.configuracion_routes import build_page

    QApplication.instance() or QApplication([])
    _rol(conn)
    _usuario(conn)

    pagina = build_page(
        "config_usuarios_roles",
        ConfiguracionPresenter(query_service=_servicio(conn)))

    assert type(pagina).__name__ == "UsuariosRolesPage"
    # 7 roles sembrados + el creado aquí.
    assert pagina.roles_table.rowCount() == 8
