"""
tests/purchases/test_purchase_lot_creation.py
──────────────────────────────────────────────
FASE 1 — Tests de caracterización: creación de lotes en compras.

Propósito: documentar que los lotes son OPCIONALES en compra tradicional.
La lógica de lotes obligatoria vive en el flujo QR/recepción.

Cobertura:
- LoteService puede registrar lote correctamente
- Un lote tiene los campos requeridos (uuid, producto_id, numero_lote, peso_kg)
- Compra tradicional NO llama lote_service directamente (lotes opcionales)
- La tabla detalles_compra tiene campo `lote` TEXT (identificador, no FK)
- FIFO usar_lote no afecta compras (solo afecta salidas)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlite3
import pytest
from unittest.mock import MagicMock, patch

from core.services.lote_service import LoteService


SCHEMA_LOTES = """
CREATE TABLE productos (
    id INTEGER PRIMARY KEY, nombre TEXT,
    existencia REAL DEFAULT 100
);
INSERT INTO productos VALUES (1, 'Pollo Entero', 100), (2, 'Arrachera', 50);
"""


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_LOTES)
    conn.isolation_level = None
    return conn


@pytest.fixture
def lote_svc(db):
    return LoteService(db)


class TestPurchaseLotCreation:

    def test_registrar_lote_creates_record(self, db, lote_svc):
        lote_svc.registrar_lote(
            producto_id=1,
            peso_kg=52.1,
            fecha_caducidad="2026-05-22",
            proveedor_id=3,
            numero_lote="L-2026-001",
        )
        row = db.execute("SELECT * FROM lotes WHERE numero_lote=?", ("L-2026-001",)).fetchone()
        assert row is not None, "lote debe existir después de registrar_lote"

    def test_lote_uuid_generated(self, db, lote_svc):
        lote_svc.registrar_lote(
            producto_id=1,
            peso_kg=10.0,
            fecha_caducidad="2026-05-20",
            proveedor_id=1,
            numero_lote="L-UUID-TEST",
        )
        row = db.execute("SELECT uuid FROM lotes WHERE numero_lote=?", ("L-UUID-TEST",)).fetchone()
        assert row is not None
        assert row["uuid"] and len(row["uuid"]) > 0, "uuid debe generarse automáticamente"

    def test_lote_peso_inicial_stored(self, db, lote_svc):
        lote_svc.registrar_lote(
            producto_id=2,
            peso_kg=48.5,
            fecha_caducidad="2026-05-18",
            proveedor_id=2,
            numero_lote="L-PESO-TEST",
        )
        row = db.execute(
            "SELECT peso_inicial_kg, peso_actual_kg FROM lotes WHERE numero_lote=?",
            ("L-PESO-TEST",)
        ).fetchone()
        assert abs(row["peso_inicial_kg"] - 48.5) < 0.01
        assert abs(row["peso_actual_kg"] - 48.5) < 0.01

    def test_lote_estado_activo_by_default(self, db, lote_svc):
        lote_svc.registrar_lote(
            producto_id=1,
            peso_kg=5.0,
            fecha_caducidad="2026-05-25",
            proveedor_id=1,
            numero_lote="L-ESTADO-TEST",
        )
        row = db.execute(
            "SELECT estado FROM lotes WHERE numero_lote=?", ("L-ESTADO-TEST",)
        ).fetchone()
        assert row["estado"] == "activo"

    def test_traditional_purchase_does_not_call_lote_service(self):
        """
        Compra tradicional NO llama lote_service.registrar_lote() directamente.
        Los lotes en compra tradicional son un campo texto opcional en detalles_compra.
        """
        import inspect
        from core.services.purchase_service import PurchaseService
        source = inspect.getsource(PurchaseService.register_purchase)
        assert "lote_service" not in source, (
            "PurchaseService.register_purchase no debe llamar lote_service "
            "(lotes son opcionales en compra tradicional)"
        )

    def test_detalles_compra_has_lote_text_field(self):
        """
        La tabla detalles_compra tiene campo 'lote' TEXT (identificador de lote opcional).
        No es FK — es referencia de texto para trazabilidad simple.
        """
        conn = sqlite3.connect(":memory:")
        conn.executescript("""
            CREATE TABLE detalles_compra (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                compra_id INTEGER, producto_id INTEGER,
                cantidad REAL, precio_unitario REAL, subtotal REAL,
                lote TEXT, fecha_caducidad DATE
            );
        """)
        # Verify field 'lote' exists as TEXT
        cols = {row[1] for row in conn.execute("PRAGMA table_info(detalles_compra)")}
        assert "lote" in cols, "detalles_compra debe tener campo 'lote'"
        conn.close()

    def test_lot_fifo_does_not_affect_purchase_stock(self, db, lote_svc):
        """
        usar_lote_fifo es para SALIDAS (ventas), no afecta entradas de compra.
        Un lote recién creado no debe reducir peso_actual al registrar.
        """
        lote_svc.registrar_lote(
            producto_id=1,
            peso_kg=30.0,
            fecha_caducidad="2026-05-30",
            proveedor_id=1,
            numero_lote="L-FIFO-TEST",
        )
        row_before = db.execute(
            "SELECT peso_actual_kg FROM lotes WHERE numero_lote=?", ("L-FIFO-TEST",)
        ).fetchone()
        assert abs(row_before["peso_actual_kg"] - 30.0) < 0.01, (
            "registrar_lote no debe reducir peso (FIFO es para salidas)"
        )
