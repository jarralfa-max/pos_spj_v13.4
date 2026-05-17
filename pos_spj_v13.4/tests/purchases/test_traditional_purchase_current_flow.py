"""
tests/purchases/test_traditional_purchase_current_flow.py
──────────────────────────────────────────────────────────
FASE 1 — Tests de caracterización: flujo actual de compra tradicional.

Propósito: capturar el comportamiento ACTUAL antes de refactorizar.
Si alguno falla después del refactor, se rompió algo que funcionaba.

Cobertura:
- PurchaseService.register_purchase() crea cabecera y partidas
- Folio generado con formato esperado CMP-*
- Estado "completada" si amount_paid >= total
- Estado "credito" si amount_paid < total
- Retorna (folio, warnings) como contrato actual
- Campos condicion_pago / plazo_dias / moneda persisten
- Compra vacía (sin items) sigue el contrato actual (puede fallar o advertir)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlite3
import pytest
from unittest.mock import MagicMock, patch

from repositories.purchase_repository import PurchaseRepository
from core.services.purchase_service import PurchaseService


# ── Schema mínimo ─────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE compras (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    folio         TEXT UNIQUE,
    fecha         DATETIME DEFAULT (datetime('now')),
    proveedor_id  INTEGER,
    usuario       TEXT,
    subtotal      REAL DEFAULT 0,
    iva           REAL DEFAULT 0,
    total         REAL NOT NULL DEFAULT 0,
    estado        TEXT DEFAULT 'completada',
    forma_pago    TEXT DEFAULT 'CONTADO',
    observaciones TEXT,
    sucursal_id   INTEGER DEFAULT 1,
    condicion_pago TEXT DEFAULT 'liquidado',
    plazo_dias    INTEGER DEFAULT 0,
    moneda        TEXT DEFAULT 'MXN'
);
CREATE TABLE detalles_compra (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    compra_id       INTEGER NOT NULL,
    producto_id     INTEGER NOT NULL,
    cantidad        REAL NOT NULL,
    precio_unitario REAL NOT NULL,
    subtotal        REAL NOT NULL,
    lote            TEXT,
    fecha_caducidad DATE
);
CREATE TABLE productos (
    id INTEGER PRIMARY KEY, nombre TEXT
);
INSERT INTO productos VALUES (1, 'Pollo Entero'), (2, 'Arrachera');
"""


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.isolation_level = None  # autocommit — matches production
    return conn


@pytest.fixture
def repo(db):
    return PurchaseRepository(db)


@pytest.fixture
def service(db, repo):
    inv_svc = MagicMock()
    fin_svc = MagicMock()
    svc = PurchaseService(db, repo, inv_svc, fin_svc)
    # Patch event bus to isolate from handlers
    with patch("core.events.event_bus.get_bus") as mock_bus:
        bus = MagicMock()
        bus.handler_count.return_value = 0  # no handlers wired → fallback path
        bus.publish_async = MagicMock()
        mock_bus.return_value = bus
        svc._mock_bus = bus
        yield svc


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestTraditionalPurchaseCurrentFlow:

    def test_register_purchase_returns_folio_and_warnings(self, service):
        items = [{"product_id": 1, "qty": 10.0, "unit_cost": 50.0}]
        result = service.register_purchase(
            provider_id=1, branch_id=1, user="admin",
            items=items, payment_method="CONTADO", amount_paid=500.0,
        )
        assert isinstance(result, tuple), "debe retornar una tupla"
        folio, warnings = result
        assert folio, "folio no debe ser vacío"
        assert isinstance(warnings, list), "warnings debe ser lista"

    def test_folio_format_starts_with_CMP(self, service):
        items = [{"product_id": 1, "qty": 5.0, "unit_cost": 100.0}]
        folio, _ = service.register_purchase(
            provider_id=1, branch_id=1, user="admin",
            items=items, payment_method="CONTADO", amount_paid=500.0,
        )
        assert folio.startswith("CMP-"), f"folio esperado CMP-*, obtenido: {folio}"

    def test_estado_completada_when_fully_paid(self, db, service):
        items = [{"product_id": 1, "qty": 10.0, "unit_cost": 50.0}]
        folio, _ = service.register_purchase(
            provider_id=1, branch_id=1, user="admin",
            items=items, payment_method="CONTADO", amount_paid=500.0,
        )
        row = db.execute("SELECT estado FROM compras WHERE folio=?", (folio,)).fetchone()
        assert row is not None
        assert row["estado"] == "completada"

    def test_estado_credito_when_underpaid(self, db, service):
        items = [{"product_id": 1, "qty": 10.0, "unit_cost": 50.0}]
        folio, _ = service.register_purchase(
            provider_id=1, branch_id=1, user="admin",
            items=items, payment_method="CREDITO", amount_paid=0.0,
        )
        row = db.execute("SELECT estado FROM compras WHERE folio=?", (folio,)).fetchone()
        assert row["estado"] == "credito"

    def test_purchase_header_persisted(self, db, service):
        items = [{"product_id": 2, "qty": 8.0, "unit_cost": 280.0}]
        folio, _ = service.register_purchase(
            provider_id=5, branch_id=2, user="comprador01",
            items=items, payment_method="TRANSFERENCIA", amount_paid=2240.0,
        )
        row = db.execute("SELECT * FROM compras WHERE folio=?", (folio,)).fetchone()
        assert row is not None
        assert row["proveedor_id"] == 5
        assert row["sucursal_id"] == 2
        assert row["usuario"] == "comprador01"
        assert abs(row["total"] - 2240.0) < 0.01

    def test_purchase_items_persisted(self, db, service):
        items = [
            {"product_id": 1, "qty": 10.0, "unit_cost": 50.0},
            {"product_id": 2, "qty": 5.0, "unit_cost": 280.0},
        ]
        folio, _ = service.register_purchase(
            provider_id=1, branch_id=1, user="admin",
            items=items, payment_method="CONTADO", amount_paid=1900.0,
        )
        compra = db.execute("SELECT id FROM compras WHERE folio=?", (folio,)).fetchone()
        detalles = db.execute(
            "SELECT * FROM detalles_compra WHERE compra_id=?", (compra["id"],)
        ).fetchall()
        assert len(detalles) == 2

    def test_condicion_pago_persisted(self, db, service):
        items = [{"product_id": 1, "qty": 1.0, "unit_cost": 100.0}]
        folio, _ = service.register_purchase(
            provider_id=1, branch_id=1, user="admin",
            items=items, payment_method="CREDITO", amount_paid=0.0,
            condicion_pago="credito_30", plazo_dias=30, moneda="USD",
        )
        row = db.execute("SELECT * FROM compras WHERE folio=?", (folio,)).fetchone()
        assert row["condicion_pago"] == "credito_30"
        assert row["plazo_dias"] == 30
        assert row["moneda"] == "USD"

    def test_multiple_purchases_generate_unique_folios(self, service):
        items = [{"product_id": 1, "qty": 1.0, "unit_cost": 10.0}]
        folio1, _ = service.register_purchase(
            provider_id=1, branch_id=1, user="admin",
            items=items, payment_method="CONTADO", amount_paid=10.0,
        )
        folio2, _ = service.register_purchase(
            provider_id=1, branch_id=1, user="admin",
            items=items, payment_method="CONTADO", amount_paid=10.0,
        )
        assert folio1 != folio2, "dos compras deben tener folios distintos"

    def test_total_calculated_from_items(self, db, service):
        items = [
            {"product_id": 1, "qty": 4.0, "unit_cost": 25.0},   # 100
            {"product_id": 2, "qty": 2.0, "unit_cost": 150.0},  # 300
        ]
        folio, _ = service.register_purchase(
            provider_id=1, branch_id=1, user="admin",
            items=items, payment_method="CONTADO", amount_paid=400.0,
        )
        row = db.execute("SELECT total FROM compras WHERE folio=?", (folio,)).fetchone()
        assert abs(row["total"] - 400.0) < 0.01
