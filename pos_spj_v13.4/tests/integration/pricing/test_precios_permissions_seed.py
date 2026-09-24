"""Migración 260 — que las acciones de PRECIOS lleguen de verdad a `rol_permisos`.

Migrar el vocabulario a `PRECIOS.<accion>` sólo lo hizo OTORGABLE. Medido en la
base viva: `rol_permisos` tenía CERO filas de `PRECIOS`, así que el módulo
seguía siendo operable únicamente por `admin` —que pasa por comodín de nombre de
rol, sin mirar la base— y ni siquiera el dueño de la instalación podía autorizar
un precio bajo mínimo.
"""

import importlib
import sqlite3

import pytest

from backend.application.pricing.permissions import ALL_PRICING_PERMISSIONS

_migracion = importlib.import_module("migrations.standalone.260_seed_precios_permissions")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(
        """
        CREATE TABLE roles (
            id TEXT NOT NULL PRIMARY KEY, nombre TEXT NOT NULL,
            descripcion TEXT, activo INTEGER DEFAULT 1);
        CREATE TABLE rol_permisos (
            id TEXT NOT NULL PRIMARY KEY, rol_id TEXT NOT NULL,
            modulo TEXT NOT NULL, accion TEXT NOT NULL,
            permitido INTEGER DEFAULT 1,
            UNIQUE(rol_id, modulo, accion));
        """)
    for rol in ("admin", "gerente", "cajero", "system_owner"):
        c.execute("INSERT INTO roles (id, nombre) VALUES (?,?)", (f"id-{rol}", rol))
    c.commit()
    yield c
    c.close()


def _acciones(conn, rol: str) -> set[str]:
    return {r[0] for r in conn.execute(
        "SELECT accion FROM rol_permisos rp JOIN roles r ON r.id = rp.rol_id "
        "WHERE r.nombre=? AND rp.modulo='PRECIOS'", (rol,))}


def test_la_lista_sembrada_coincide_con_el_vocabulario_del_contexto(conn):
    """Ata la lista transcrita en la migración al vocabulario vivo.

    La migración transcribe las acciones en vez de importarlas (una migración es
    una foto fija). Ese precio se paga con este test: una errata o una acción
    olvidada se ven aquí, no en producción.
    """
    declaradas = {c.split(".", 1)[1] for c in ALL_PRICING_PERMISSIONS}
    assert set(_migracion._TODAS) == declaradas
    assert len(_migracion._TODAS) == len(declaradas) == 23


def test_el_dueno_de_la_instalacion_recibe_todo(conn):
    """`system_owner` NO entra por `ADMIN_ROLE_NAMES`, así que sin esta siembra
    no podría autorizar un precio bajo mínimo aunque `is_admin()` diga que sí."""
    _migracion.run(conn)
    assert _acciones(conn, "system_owner") == set(_migracion._TODAS)


def test_admin_recibe_todo(conn):
    _migracion.run(conn)
    assert _acciones(conn, "admin") == set(_migracion._TODAS)


def test_el_gerente_puede_autorizar_bajo_el_minimo(conn):
    """Es la acción que hace alcanzable la autorización en caliente."""
    _migracion.run(conn)
    assert "precio.minimo.excepcion" in _acciones(conn, "gerente")


def test_el_gerente_no_gestiona_costos_ni_configuracion(conn):
    """El costo lo fija Finanzas/Compras, no quien vende."""
    _migracion.run(conn)
    del_gerente = _acciones(conn, "gerente")
    for prohibida in ("costo.gestionar", "costo.estandar.fijar",
                      "configuracion.ver", "configuracion.gestionar"):
        assert prohibida not in del_gerente
    # Ver el costo sí, gestionarlo no: son permisos distintos por diseño.
    assert "costo.ver" in del_gerente


def test_el_cajero_no_recibe_nada(conn):
    """Conceder 'por si acaso' es lo contrario de fallar cerrado."""
    _migracion.run(conn)
    assert _acciones(conn, "cajero") == set()


def test_es_idempotente(conn):
    """`rol_permisos` declara UNIQUE(rol_id, modulo, accion); sin esa
    restricción `INSERT OR IGNORE` duplicaría permisos al reejecutarse."""
    _migracion.run(conn)
    primero = conn.execute(
        "SELECT COUNT(*) FROM rol_permisos WHERE modulo='PRECIOS'").fetchone()[0]
    _migracion.run(conn)
    segundo = conn.execute(
        "SELECT COUNT(*) FROM rol_permisos WHERE modulo='PRECIOS'").fetchone()[0]
    assert primero == segundo > 0


def test_un_rol_ausente_se_omite_sin_crearlo(conn):
    """Inventar roles desde una migración de permisos daría acceso a una
    identidad que nadie definió."""
    conn.execute("DELETE FROM roles WHERE nombre='gerente'")
    conn.commit()

    _migracion.run(conn)

    assert conn.execute(
        "SELECT COUNT(*) FROM roles WHERE nombre='gerente'").fetchone()[0] == 0
    assert _acciones(conn, "system_owner") == set(_migracion._TODAS)


def test_sin_tablas_de_seguridad_no_revienta(conn):
    """Una base parcial no debe tumbar la cadena de migraciones."""
    conn.executescript("DROP TABLE rol_permisos; DROP TABLE roles;")
    conn.commit()
    _migracion.run(conn)  # no lanza


def test_el_rol_se_busca_sin_distinguir_mayusculas(conn):
    """Mismo criterio que `SqlitePermissionRepository.role_id_for_name`: un rol
    guardado como 'Gerente' debe encontrarse igual."""
    conn.execute("UPDATE roles SET nombre='Gerente' WHERE nombre='gerente'")
    conn.commit()

    _migracion.run(conn)

    assert "precio.minimo.excepcion" in _acciones(conn, "Gerente")
