"""CRM-43 — base con TODAS las migraciones (como la app real), usuarios por
rol con los permisos que ``rol_permisos`` les da, y el presentador REAL de
``customers_crm_factory`` (nunca un verificador permisivo de pruebas).

La plantilla se construye una vez por sesión (el motor tarda ~9 s) y cada
prueba trabaja sobre una copia en memoria.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.shared.ids import new_uuid


@pytest.fixture(scope="session")
def crm43_template():
    from migrations import engine

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    engine.up(conn)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def conn(crm43_template):
    copy = sqlite3.connect(":memory:")
    copy.row_factory = sqlite3.Row
    crm43_template.backup(copy)
    yield copy
    copy.close()


def branch_id(conn) -> str:
    return conn.execute("SELECT id FROM sucursales ORDER BY rowid LIMIT 1").fetchone()[0]


def add_branch(conn, name: str) -> str:
    bid = new_uuid()
    conn.execute("INSERT INTO sucursales (id, nombre) VALUES (?, ?)", (bid, name))
    conn.commit()
    return bid


def add_user(conn, role: str, *, name: str | None = None, branch: str | None = None) -> str:
    uid = new_uuid()
    conn.execute(
        "INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, sucursal_id, activo)"
        " VALUES (?,?,?,?,?,?,1)",
        (uid, name or role, f"{role}-{uid[-6:]}", "x", role, branch or branch_id(conn)))
    conn.commit()
    return uid


def session_for(conn, user_id: str, role: str, branch: str | None = None):
    from backend.application.security.permission_query_service import PermissionQueryService
    from backend.bootstrap.application_context import ApplicationContext, FeatureContext
    from backend.bootstrap.legacy_session_adapter import LegacySessionAdapter
    from backend.infrastructure.db.repositories.security.permission_repository import (
        SqlitePermissionRepository,
    )

    branch = branch or branch_id(conn)
    perms = PermissionQueryService(SqlitePermissionRepository(conn)).permission_codes_for_user(
        user_id, branch)
    ctx = ApplicationContext(
        installation_id="", company_id="", branch_id=branch, branch_name="Centro",
        assigned_branch_ids=frozenset({branch}), workstation_id="ws", workstation_type="",
        user_id=user_id, user_name=role, roles=(role,), permissions=frozenset(perms),
        feature_context=FeatureContext.from_flags_dict({}), session_id=new_uuid())
    return LegacySessionAdapter(ctx)


def presenter_for(conn, role: str, *, branch: str | None = None, user_id: str | None = None):
    from backend.infrastructure.desktop.customers_crm_factory import (
        build_customers_crm_presenter,
    )
    uid = user_id or add_user(conn, role, branch=branch)
    return build_customers_crm_presenter(conn, session_for(conn, uid, role, branch)), uid


def new_customer(presenter, name: str = "Restaurante El Sol", **kwargs):
    result = presenter.run("create_customer", display_name=name, **kwargs)
    assert result.success, result.message
    return result.entity_id


def add_product(conn, name: str, price: str, *, unit: str = "PZA", min_price: str | None = None,
                branch: str | None = None) -> str:
    """Producto vendible, habilitado en la sucursal, con precio en la lista BASE
    activa (la que siembra el motor)."""
    from decimal import Decimal

    from backend.domain.pricing.entities.product_price import ProductPrice
    from backend.domain.pricing.value_objects.money import Money
    from backend.infrastructure.db.repositories.pricing.pricing_repository import (
        PricingRepository,
    )

    pid = new_uuid()
    unit_id = conn.execute("SELECT id FROM units_of_measure WHERE code=?", (unit,)).fetchone()[0]
    conn.execute(
        "INSERT INTO products (id, code, name, name_normalized, product_type, lifecycle_status,"
        " base_unit_id, sellable, internal_only) VALUES (?,?,?,?,?,?,?,1,0)",
        (pid, f"P-{pid[-6:]}", name, name.lower(), "RESALE_PRODUCT", "ACTIVE", unit_id))
    conn.execute("INSERT INTO branch_product (id, product_id, branch_id, enabled) VALUES (?,?,?,1)",
                 (new_uuid(), pid, branch or branch_id(conn)))
    base = conn.execute("SELECT id FROM price_list WHERE kind='BASE' AND status='ACTIVE'"
                        ).fetchone()[0]
    PricingRepository(conn).save_price(ProductPrice(
        price_list_id=base, product_id=pid, sale_price=Money(Decimal(price)),
        min_price=Money(Decimal(min_price)) if min_price else None))
    conn.commit()
    return pid
