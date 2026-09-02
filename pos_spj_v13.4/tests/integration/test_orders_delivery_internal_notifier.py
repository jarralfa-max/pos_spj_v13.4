"""ORD-26 — OrdersDeliveryInternalNotifier, against the REAL canonical
`usuarios`/`usuarios_roles`/`roles`/`notification_inbox` schema (m000), plus
the orders_delivery/inventory schemas layered on top (all `CREATE TABLE IF
NOT EXISTS`, so layering is safe)."""

from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.orders_delivery_schema import create_orders_delivery_schema
from backend.infrastructure.integrations.orders_delivery_internal_notifier import (
    OrdersDeliveryInternalNotifier,
)
from backend.shared.ids import new_uuid
from migrations import m000_base_schema
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    create_orders_delivery_schema(connection)
    create_inventory_schema(connection)
    yield connection
    connection.close()


def _seed_admin(conn, *, branch_id: str) -> str:
    # m000_base_schema already seeds a default 'admin' role on a fresh
    # install (roles.nombre is UNIQUE) — reuse it instead of inserting a
    # duplicate.
    user_id = new_uuid()
    role_id = conn.execute(
        "SELECT id FROM roles WHERE LOWER(nombre)='admin'").fetchone()[0]
    conn.execute(
        "INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, sucursal_id, activo)"
        " VALUES (?,?,?,?,?,?,1)",
        (user_id, "Admin", f"admin-{user_id[:8]}", "hash", "admin", branch_id))
    conn.execute(
        "INSERT INTO usuarios_roles (usuario_id, rol_id, sucursal_id) VALUES (?, ?, ?)",
        (user_id, role_id, branch_id))
    conn.commit()
    return user_id


class TestNotifyRoles:
    def test_writes_one_inbox_row_per_matching_user(self, conn):
        branch_id = new_uuid()
        admin_id = _seed_admin(conn, branch_id=branch_id)

        written = OrdersDeliveryInternalNotifier(conn).notify_roles(
            roles=("admin", "gerente"), branch_id=branch_id, tipo="entrega_fallida",
            titulo="Entrega fallida", cuerpo="Motivo: cliente ausente",
            datos={"delivery_job_id": new_uuid()})

        assert written == 1
        row = conn.execute(
            "SELECT empleado_id, tipo, titulo, sucursal_id FROM notification_inbox"
        ).fetchone()
        assert tuple(row) == (admin_id, "entrega_fallida", "Entrega fallida", branch_id)

    def test_no_matching_role_writes_nothing(self, conn):
        branch_id = new_uuid()
        _seed_admin(conn, branch_id=branch_id)

        written = OrdersDeliveryInternalNotifier(conn).notify_roles(
            roles=("finanzas",), branch_id=branch_id, tipo="x", titulo="x", cuerpo="x")

        assert written == 0
        assert conn.execute("SELECT COUNT(*) FROM notification_inbox").fetchone()[0] == 0

    def test_never_raises_on_missing_tables(self):
        # Bare orders_delivery/inventory schema, no usuarios/notification_inbox
        # at all — the notifier must degrade to a no-op, never crash the
        # delivery operation that triggered it.
        bare = sqlite3.connect(":memory:")
        create_orders_delivery_schema(bare)
        written = OrdersDeliveryInternalNotifier(bare).notify_roles(
            roles=("admin",), branch_id=new_uuid(), tipo="x", titulo="x", cuerpo="x")
        assert written == 0
        bare.close()
