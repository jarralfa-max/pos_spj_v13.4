"""Migración 267 — una base migrada con el esquema VIEJO de Delivery.

La base real tenía 226 aplicada con la forma de entonces: sin
`customer_orders.pickup_verification_code`, sin `customer_order_lines.package_id`
y sin 10 tablas posteriores. Crear cualquier pedido reventaba. Las pruebas no lo
veían porque arman el esquema desde cero; aquí se reconstruye la forma vieja.
"""
from __future__ import annotations

import importlib
import sqlite3

import pytest

from backend.infrastructure.db.schema.orders_delivery_schema import create_orders_delivery_schema
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from backend.infrastructure.db.schema.products_schema import create_products_schema
from tests.integration._audit_trail_table import create_audit_logs_table
from tests.integration.orders_delivery.test_capture_order import Catalogo, _capturar

m267 = importlib.import_module("migrations.standalone.267_orders_delivery_schema_drift")

TABLAS_POSTERIORES = (
    "order_packages", "delivery_jobs", "delivery_attempts", "driver_operational_profiles",
    "delivery_assignments", "delivery_routes", "delivery_route_stops",
    "redelivery_requests", "driver_cash_collections", "driver_settlements",
)


def _forma_vieja(conn) -> None:
    """La base real: 226 aplicada antes de que el esquema creciera."""
    create_orders_delivery_schema(conn)
    conn.execute("DROP INDEX IF EXISTS idx_customer_order_lines_package")
    conn.execute("ALTER TABLE customer_order_lines DROP COLUMN package_id")
    conn.execute("ALTER TABLE customer_orders DROP COLUMN pickup_verification_code")
    for tabla in reversed(TABLAS_POSTERIORES):
        conn.execute(f"DROP TABLE IF EXISTS {tabla}")
    conn.commit()


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    create_pricing_schema(c)
    _forma_vieja(c)
    create_audit_logs_table(c)
    c.commit()
    yield c
    c.close()


def _columnas(conn, tabla):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({tabla})")}


def test_con_la_forma_vieja_crear_un_pedido_revienta(conn):
    """El síntoma medido en la base real, fijado para que no vuelva."""
    refresco = Catalogo(conn).producto("Refresco", precio="25")
    with pytest.raises(sqlite3.OperationalError, match="pickup_verification_code"):
        _capturar(conn, [{"product_id": refresco, "quantity": "1"}])


def test_267_completa_columnas_y_tablas_y_el_pedido_se_crea(conn):
    refresco = Catalogo(conn).producto("Refresco", precio="25")

    m267.run(conn)

    assert "pickup_verification_code" in _columnas(conn, "customer_orders")
    assert "package_id" in _columnas(conn, "customer_order_lines")
    existentes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert set(TABLAS_POSTERIORES) <= existentes
    resultado = _capturar(conn, [{"product_id": refresco, "quantity": "2"}])
    assert resultado.success, resultado.message


def test_267_es_idempotente_y_no_toca_una_base_al_dia():
    c = sqlite3.connect(":memory:")
    create_orders_delivery_schema(c)
    antes = c.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()

    m267.run(c)
    m267.run(c)

    assert c.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall() == antes


def test_267_esta_registrada_en_el_motor():
    from migrations.engine import MIGRATIONS
    assert any(getattr(mig, "version", None) == "267" or "267_orders_delivery_schema_drift"
               in str(mig) for mig in MIGRATIONS)
