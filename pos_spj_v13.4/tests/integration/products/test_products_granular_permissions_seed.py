"""PROD-22 — permisos granulares de Productos: puente que falla cerrado + siembra 324.

Medido en la base real antes del cambio: ningún rol tenía un solo permiso
granular de Productos y el puente concedía cualquier código sin mapeo con la sola
vista. Estos tests recorren el camino real: `rol_permisos` → repositorio SQLite →
`PermissionQueryService` → verificador del puente → política de Productos.
"""

from __future__ import annotations

import importlib
import sqlite3

import pytest

from backend.application.products.authorization.permission_bridge import (
    SessionPermissionChecker,
    legacy_codes_for,
)
from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.permissions import (
    ALL_PRODUCT_PERMISSIONS,
    ProductPermissions as P,
)
from backend.application.security.permission_query_service import PermissionQueryService
from backend.domain.products.exceptions import ProductPermissionDeniedError
from backend.infrastructure.db.repositories.security.permission_repository import (
    SqlitePermissionRepository,
)
from backend.security.permissions.codes import normalize_permission

_MIGRATION = importlib.import_module(
    "migrations.standalone.324_seed_products_granular_permissions")

#: Lo que tenía cada rol en la base real el 2026-10-09 (sólo gruesos).
_COARSE = {
    "system_owner": ("ver", "crear", "editar", "eliminar", "exportar"),
    "gerente": ("ver", "crear", "editar", "eliminar", "exportar"),
    "almacen": ("ver", "crear", "editar"),
    "cajero": ("ver",),
    "solo_lectura": ("ver",),
}


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE roles (id TEXT PRIMARY KEY, nombre TEXT NOT NULL);
        CREATE TABLE usuarios (id TEXT PRIMARY KEY, usuario TEXT, rol TEXT);
        CREATE TABLE rol_permisos (id TEXT PRIMARY KEY, rol_id TEXT NOT NULL,
            modulo TEXT NOT NULL, accion TEXT NOT NULL, permitido INTEGER DEFAULT 1,
            UNIQUE(rol_id, modulo, accion));
    """)
    for index, (rol, acciones) in enumerate(_COARSE.items()):
        rid = f"rol-{index}"
        c.execute("INSERT INTO roles VALUES (?,?)", (rid, rol))
        c.execute("INSERT INTO usuarios VALUES (?,?,?)", (f"u-{rol}", rol, rol))
        for accion in acciones:
            c.execute("INSERT INTO rol_permisos VALUES (?,?,?,?,1)",
                      (f"{rid}-{accion}", rid, "PRODUCTOS", accion))
    c.commit()
    yield c
    c.close()


class _Session:
    """Sesión con los códigos efectivos que resuelve la app real."""

    def __init__(self, conn, rol):
        # El verificador sólo responde por el usuario de la sesión (auditoría de
        # permisos 968e0bc, PER-03), así que la sesión tiene que decir quién es.
        self.user_id = f"u-{rol}"
        self._codes = PermissionQueryService(
            SqlitePermissionRepository(conn)).permission_codes_for_user(f"u-{rol}")

    def tiene_permiso(self, code):
        return "*" in self._codes or normalize_permission(code) in self._codes


def _can(conn, rol, code) -> bool:
    return SessionPermissionChecker(_Session(conn, rol)).has_permission(f"u-{rol}", code)


# ── el puente ya no concede con la vista ────────────────────────────────────
def test_unmapped_codes_are_denied_not_granted_with_view():
    assert legacy_codes_for("PRODUCTOS.algo_inventado") == ()


@pytest.mark.parametrize("code", [
    P.BRANCH_ASSIGNMENT_MANAGE, P.ASSORTMENT_MANAGE, P.SPECIES_MANAGE, P.CUTS_MANAGE,
    P.INTERNAL_CREATE, P.EXTERNAL_APPROVE, P.SETTINGS_MANAGE, P.WHATSAPP_ALERTS_MANAGE,
    P.BARCODES_MANAGE, P.RECIPE_APPROVE, P.ACTIVATE, P.VIEW_AUDIT,
])
def test_view_only_roles_cannot_mutate_sensitive_master_data(conn, code):
    for rol in ("cajero", "solo_lectura"):
        assert not _can(conn, rol, code), (rol, code)


def test_view_only_roles_still_consult(conn):
    for code in (P.VIEW, P.SPECIES_VIEW, P.RECIPE_VIEW, P.BRANCH_ASSIGNMENT_VIEW):
        assert _can(conn, "cajero", code)


@pytest.mark.parametrize("code", [P.RECIPE_APPROVE, P.RECIPE_ACTIVATE, P.YIELD_APPROVE,
                                  P.YIELD_ACTIVATE, P.APPROVE, P.ACTIVATE,
                                  P.IMPORT_APPROVE])
def test_edit_alone_no_longer_approves_or_activates(conn, code):
    """Antes del seed, `editar` (almacen) concedía aprobar y activar."""
    assert not _can(conn, "almacen", code)


# ── la siembra 324 ──────────────────────────────────────────────────────────
def test_seed_lists_exactly_the_declared_permissions():
    declared = {code.split(".", 1)[1] for code in ALL_PRODUCT_PERMISSIONS}
    assert set(_MIGRATION._TODAS) == declared
    for rol, acciones in _MIGRATION.ASIGNACIONES.items():
        assert set(acciones) <= declared, rol


def test_after_seed_each_role_gets_its_matrix(conn):
    _MIGRATION.run(conn)
    _MIGRATION.run(conn)  # idempotente
    assert all(_can(conn, "system_owner", code) for code in ALL_PRODUCT_PERMISSIONS)
    # gerente aprueba y activa, pero no configura el módulo
    assert _can(conn, "gerente", P.RECIPE_APPROVE) and _can(conn, "gerente", P.ACTIVATE)
    assert _can(conn, "gerente", P.BRANCH_ASSIGNMENT_MANAGE)
    assert not _can(conn, "gerente", P.SETTINGS_MANAGE)
    assert not _can(conn, "gerente", P.WHATSAPP_ALERTS_MANAGE)
    # almacén captura, no aprueba ni habilita por sucursal
    assert _can(conn, "almacen", P.INTERNAL_CREATE) and _can(conn, "almacen", P.CUTS_MANAGE)
    assert not _can(conn, "almacen", P.RECIPE_APPROVE)
    assert not _can(conn, "almacen", P.BRANCH_ASSIGNMENT_MANAGE)
    # cajero y solo_lectura no reciben nada nuevo
    assert not _can(conn, "cajero", P.BRANCH_ASSIGNMENT_MANAGE)
    rows = conn.execute("SELECT COUNT(*) FROM rol_permisos r JOIN roles x ON x.id=r.rol_id "
                        "WHERE x.nombre IN ('cajero','solo_lectura')").fetchone()[0]
    assert rows == 2


def test_seed_skips_roles_that_do_not_exist(conn):
    conn.execute("DELETE FROM roles WHERE nombre='almacen'")
    _MIGRATION.run(conn)
    assert conn.execute("SELECT COUNT(*) FROM roles").fetchone()[0] == 4


def test_seed_never_revokes_a_manual_denial(conn):
    rid = conn.execute("SELECT id FROM roles WHERE nombre='gerente'").fetchone()[0]
    conn.execute("INSERT INTO rol_permisos VALUES ('x', ?, 'PRODUCTOS', 'receta.aprobar', 0)",
                 (rid,))
    _MIGRATION.run(conn)
    assert not _can(conn, "gerente", P.RECIPE_APPROVE)


# ── la política del backend usa el mismo verificador ────────────────────────
def test_backend_policy_rejects_a_cashier_enabling_a_product_in_a_branch(conn):
    policy = ProductsAuthorizationPolicy(SessionPermissionChecker(_Session(conn, "cajero")))
    with pytest.raises(ProductPermissionDeniedError):
        policy.require("u-cajero", P.BRANCH_ASSIGNMENT_MANAGE)
