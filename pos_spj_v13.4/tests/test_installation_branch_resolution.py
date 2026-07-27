# tests/test_installation_branch_resolution.py — SPJ POS v13.4
"""
F10 — Tests del bug de propagación de sucursal de instalación.

Cubre el contrato canónico de 3 estados (core/services/branch_resolution.py),
los filtros de identidad válida en ConfigRepository, la ausencia de fallbacks
'Principal' en AuthRepository y el cableado de propagación post-login.

Evidencia original del bug:
    configuraciones.sucursal_instalacion_id = 'None'  (string literal)
    sucursales: (None, 'Cadenas', ...)                (id NULL)
"""
import os
import sqlite3

import pytest

from backend.shared.ids import new_uuid
from core.services.branch_resolution import (
    INSTALLATION_BRANCH_KEY,
    is_invalid_identity,
    resolve_installation_branch,
)
from repositories.auth_repository import AuthRepository
from repositories.config_repository import ConfigRepository

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(relpath: str) -> str:
    with open(os.path.join(_ROOT, relpath), encoding="utf-8") as fh:
        return fh.read()


def _code_string_literals(relpath: str) -> list:
    """Literales string del CÓDIGO (excluye comentarios y docstrings)."""
    import ast
    tree = ast.parse(_read(relpath))
    doc_ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef,
                             ast.FunctionDef, ast.AsyncFunctionDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)):
                doc_ids.add(id(node.body[0].value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in doc_ids]


@pytest.fixture
def branch_db():
    """BD mínima: configuraciones + sucursales + usuarios (born-clean)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE configuraciones (
            clave TEXT PRIMARY KEY, valor TEXT,
            tipo TEXT DEFAULT 'texto', grupo TEXT DEFAULT 'general',
            descripcion TEXT
        );
        CREATE TABLE sucursales (
            id TEXT PRIMARY KEY, nombre TEXT NOT NULL,
            direccion TEXT, telefono TEXT,
            activa INTEGER DEFAULT 1,
            fecha_alta TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE usuarios (
            id TEXT PRIMARY KEY, usuario TEXT UNIQUE, nombre TEXT,
            password_hash TEXT, rol TEXT, sucursal_id TEXT,
            activo INTEGER DEFAULT 1
        );
    """)
    yield conn
    conn.close()


def _seed_cadenas(conn) -> str:
    """Siembra Principal + Cadenas (ambas válidas) y devuelve el id de Cadenas."""
    principal_id = new_uuid()
    cadenas_id = new_uuid()
    conn.execute(
        "INSERT INTO sucursales (id, nombre, activa, fecha_alta) VALUES (?,?,1,'2024-01-01')",
        (principal_id, "Principal"),
    )
    conn.execute(
        "INSERT INTO sucursales (id, nombre, activa, fecha_alta) VALUES (?,?,1,'2024-06-01')",
        (cadenas_id, "Cadenas"),
    )
    return cadenas_id


# ── 1. El selector nunca carga sucursales con id inválido ───────────────────

def test_selector_excludes_invalid_branch_rows(branch_db):
    _seed_cadenas(branch_db)
    # Contaminación: filas con id NULL, '', 'None' y 'null' (bug original).
    branch_db.execute(
        "INSERT INTO sucursales (id, nombre, activa) VALUES (NULL, 'Fantasma1', 1)")
    branch_db.execute(
        "INSERT INTO sucursales (id, nombre, activa) VALUES ('', 'Fantasma2', 1)")
    branch_db.execute(
        "INSERT INTO sucursales (id, nombre, activa) VALUES ('None', 'Fantasma3', 1)")
    branch_db.execute(
        "INSERT INTO sucursales (id, nombre, activa) VALUES ('null', 'Fantasma4', 1)")

    repo = ConfigRepository(branch_db)
    for metodo in (repo.active_branches_for_selector,
                   repo.branches_for_company_settings):
        pares = metodo()
        nombres = [n for _, n in pares]
        assert set(nombres) == {"Principal", "Cadenas"}, metodo.__name__
        for sid, _ in pares:
            assert not is_invalid_identity(sid), metodo.__name__

    nombres_all = [b["nombre"] for b in repo.get_all_branches()]
    assert set(nombres_all) == {"Principal", "Cadenas"}


# ── 2. Configuración nunca guarda "None" como sucursal de instalación ───────

def test_config_never_saves_none_as_installation_branch(branch_db):
    _seed_cadenas(branch_db)
    repo = ConfigRepository(branch_db)
    for invalido in (None, "", "None", "null", "  none  "):
        with pytest.raises(ValueError):
            repo.set_installation_branch(invalido)
    row = branch_db.execute(
        "SELECT valor FROM configuraciones WHERE clave=?",
        (INSTALLATION_BRANCH_KEY,),
    ).fetchone()
    assert row is None, "no debe haberse guardado ninguna clave"

    # La UI también rechaza el valor antes de llegar al repositorio.
    src = _read("modulos/configuracion.py")
    assert '"none", "null"' in src.lower() or "'none', 'null'" in src.lower()
    assert "str(None)" not in src


# ── 3. Login: configuración inválida → no configurada, nunca 'Principal' ────

def test_login_reader_invalid_config_never_falls_back_to_principal(branch_db):
    _seed_cadenas(branch_db)
    for valor in ("None", "", "null", new_uuid()):  # último: UUID inexistente
        branch_db.execute("DELETE FROM configuraciones")
        branch_db.execute(
            "INSERT INTO configuraciones (clave, valor) VALUES (?,?)",
            (INSTALLATION_BRANCH_KEY, valor),
        )
        res = resolve_installation_branch(branch_db)
        assert res["configured"] is False, valor
        assert res["id"] is None, valor
        assert res["nombre"] == "", valor
        assert res["nombre"] != "Principal"
        assert res["error"]

    # Sucursal configurada pero INACTIVA → también inválida.
    branch_db.execute("DELETE FROM configuraciones")
    inactiva = new_uuid()
    branch_db.execute(
        "INSERT INTO sucursales (id, nombre, activa) VALUES (?, 'Cerrada', 0)",
        (inactiva,),
    )
    branch_db.execute(
        "INSERT INTO configuraciones (clave, valor) VALUES (?,?)",
        (INSTALLATION_BRANCH_KEY, inactiva),
    )
    res = resolve_installation_branch(branch_db)
    assert res["configured"] is False and res["id"] is None


# ── 4. Login: configuración válida → resuelve Cadenas ───────────────────────

def test_login_reader_valid_config_resolves_cadenas(branch_db):
    cadenas_id = _seed_cadenas(branch_db)
    branch_db.execute(
        "INSERT INTO configuraciones (clave, valor) VALUES (?,?)",
        (INSTALLATION_BRANCH_KEY, cadenas_id),
    )
    res = resolve_installation_branch(branch_db)
    assert res == {"id": cadenas_id, "nombre": "Cadenas",
                   "configured": True, "pending": False, "error": ""}


# ── 4b. Clave AUSENTE → bootstrap provisional marcado como pendiente ────────

def test_missing_key_uses_first_valid_active_as_pending(branch_db):
    _seed_cadenas(branch_db)
    branch_db.execute(
        "INSERT INTO sucursales (id, nombre, activa) VALUES (NULL, 'Rota', 1)")
    res = resolve_installation_branch(branch_db)
    assert res["pending"] is True
    assert res["configured"] is False
    assert res["nombre"] == "Principal"  # primera activa por fecha_alta, VÁLIDA
    assert not is_invalid_identity(res["id"])


# ── 5. AppContainer: configuración inválida → sucursal vacía, no Principal ──

def test_app_container_uses_canonical_resolution_without_principal_fallback():
    src = _read("core/app_container.py")
    assert "resolve_installation_branch" in src
    # Sin fallback silencioso: ni JOIN propio a la clave ni primera-activa.
    init_head = src[:src.index("CAPA 1: REPOSITORIOS")]
    assert "ORDER BY fecha_alta" not in init_head
    assert 'self.sucursal_id = ""' in init_head
    # 'Principal' no existe como literal de código en el container.
    literales = _code_string_literals("core/app_container.py")
    assert not any(lit == "Principal" or "'Principal'" in lit
                   for lit in literales)
    # set_session_user no sobreescribe una terminal válida con basura.
    assert "usuario sin sucursal válida" in src


# ── 6. AuthRepository no inventa 'Principal' ni IDs default ──────────────────

def test_auth_repository_does_not_invent_principal(branch_db):
    cadenas_id = _seed_cadenas(branch_db)
    uid_ok = new_uuid()
    uid_sin = new_uuid()
    branch_db.execute(
        "INSERT INTO usuarios (id, usuario, nombre, password_hash, rol, sucursal_id, activo)"
        " VALUES (?,?,?,?,?,?,1)",
        (uid_ok, "cajero1", "Cajero Uno", "x", "cajero", cadenas_id),
    )
    branch_db.execute(
        "INSERT INTO usuarios (id, usuario, nombre, password_hash, rol, sucursal_id, activo)"
        " VALUES (?,?,?,?,?,?,1)",
        (uid_sin, "cajero2", "Cajero Dos", "x", "cajero", "None"),
    )
    repo = AuthRepository(branch_db)

    ok = repo.get_user_by_username("cajero1")
    assert ok["sucursal_id"] == cadenas_id
    assert ok["sucursal_nombre"] == "Cadenas"
    assert [s["nombre"] for s in ok["sucursales_disponibles"]] == ["Cadenas"]

    sin = repo.get_user_by_username("cajero2")
    assert sin["sucursal_id"] == ""
    assert sin["sucursal_nombre"] == ""
    assert sin["sucursales_disponibles"] == []

    literales = _code_string_literals("repositories/auth_repository.py")
    assert not any(lit == "Principal" or "'Principal'" in lit
                   for lit in literales)
    src = _read("repositories/auth_repository.py")
    assert "sucursal_id'] if has_suc else 1" not in src


# ── 7. Propagación post-login usa la sucursal de la terminal ────────────────

def test_post_login_propagation_uses_terminal_branch():
    src = _read("interfaz/main_window.py")
    # El login inyecta la sucursal de instalación en el resultado.
    assert "resultado['sucursal_id'] = inst['id']" in src
    # El lector del login delega en la ruta canónica única.
    assert "resolve_installation_branch" in src
    # _propagar_usuario ya no resuelve "primera activa" por su cuenta:
    # prefiere la sucursal del container (semántica 3 estados).
    inicio = src.index("def _propagar_usuario")
    fin = src.index("def aplicar_sucursal_activa")
    cuerpo = src[inicio:fin]
    assert "ORDER BY fecha_alta" not in cuerpo
    assert 'getattr(self.container, "sucursal_id"' in cuerpo
    assert "set_sucursal_activa" in cuerpo          # propaga al container
    assert "ACTIVE_BRANCH_CHANGED" in cuerpo        # y publica el evento
    # Propagación EN VIVO al cambiar la sucursal desde Configuración.
    assert "def aplicar_sucursal_activa" in src
    cfg = _read("modulos/configuracion.py")
    assert "aplicar_sucursal_activa" in cfg
    assert "set_installation_branch" in cfg
