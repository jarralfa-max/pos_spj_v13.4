"""
test_finance_service_methods.py — v13.4
Verifica los 6 métodos nuevos de FinanceService.
"""
import sqlite3
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_db():
    """DB en memoria con tablas mínimas para los tests de FinanceService."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE financial_event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            evento TEXT NOT NULL,
            modulo TEXT NOT NULL,
            referencia_id INTEGER,
            monto DECIMAL(15,4),
            cuenta_debe TEXT,
            cuenta_haber TEXT,
            usuario_id INTEGER,
            sucursal_id INTEGER DEFAULT 1,
            metadata JSON
        );

        CREATE TABLE productos (
            id INTEGER PRIMARY KEY,
            nombre TEXT,
            precio REAL DEFAULT 0,
            precio_costo REAL DEFAULT 50.0
        );
        INSERT INTO productos (id, nombre, precio, precio_costo) VALUES (1, 'Pollo', 100.0, 50.0);
        INSERT INTO productos (id, nombre, precio, precio_costo) VALUES (2, 'Sin costo', 100.0, 0.0);

        CREATE TABLE clientes (
            id INTEGER PRIMARY KEY,
            nombre TEXT,
            limite_credito REAL DEFAULT 1000.0
        );
        INSERT INTO clientes (id, nombre, limite_credito) VALUES (1, 'Cliente A', 500.0);

        CREATE TABLE cuentas_por_cobrar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            saldo_pendiente REAL,
            estado TEXT DEFAULT 'pendiente'
        );

        CREATE TABLE ventas (
            id INTEGER PRIMARY KEY,
            total REAL
        );
        INSERT INTO ventas VALUES (1, 200.0);

        CREATE TABLE venta_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id INTEGER,
            producto_id INTEGER,
            cantidad REAL
        );
        INSERT INTO venta_items (venta_id, producto_id, cantidad) VALUES (1, 1, 2.0);

        CREATE TABLE anticipos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id INTEGER,
            monto REAL,
            estado TEXT,
            usuario_id INTEGER,
            sucursal_id INTEGER
        );
    """)
    return conn


def _make_service(conn):
    from core.services.enterprise.finance_service import FinanceService
    return FinanceService(conn)


class TestRegistrarAsiento:
    def test_inserts_row(self):
        conn = _make_db()
        svc = _make_service(conn)
        row_id = svc.registrar_asiento(
            debe="caja", haber="ventas",
            concepto="Venta de prueba", monto=100.0,
        )
        assert row_id > 0
        row = conn.execute(
            "SELECT * FROM financial_event_log WHERE id=?", (row_id,)
        ).fetchone()
        assert row["cuenta_debe"] == "caja"
        assert row["cuenta_haber"] == "ventas"
        assert float(row["monto"]) == 100.0

    def test_graceful_if_table_missing(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        svc = _make_service(conn)
        result = svc.registrar_asiento("a", "b", "test", 10.0)
        assert result == 0  # no exception, returns 0


class TestObtenerLedger:
    def test_returns_entries_by_cuenta(self):
        conn = _make_db()
        svc = _make_service(conn)
        svc.registrar_asiento("caja", "ventas", "entry1", 100.0)
        svc.registrar_asiento("inventario", "caja", "entry2", 50.0)
        entries = svc.obtener_ledger("caja")
        assert len(entries) == 2  # caja aparece como debe en entry1 y como haber en entry2

    def test_returns_empty_on_missing_table(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        svc = _make_service(conn)
        assert svc.obtener_ledger("caja") == []


class TestValidarMargen:
    def test_valid_margin(self):
        conn = _make_db()
        svc = _make_service(conn)
        # producto 1: costo=50, precio=100 → margen=100% (bien por encima del 5% mínimo)
        assert svc.validar_margen(1, 100.0) is True

    def test_invalid_margin(self):
        conn = _make_db()
        svc = _make_service(conn)
        # precio apenas por encima del costo → margen < 5%
        assert svc.validar_margen(1, 50.5) is False

    def test_zero_cost_product_is_permissive(self):
        conn = _make_db()
        svc = _make_service(conn)
        # producto 2: precio_costo=0 → permisivo
        assert svc.validar_margen(2, 1.0) is True

    def test_unknown_product_is_permissive(self):
        conn = _make_db()
        svc = _make_service(conn)
        assert svc.validar_margen(9999, 10.0) is True


class TestControlarCredito:
    def test_approved_within_limit(self):
        conn = _make_db()
        svc = _make_service(conn)
        result = svc.controlar_credito(1, 300.0)
        assert result["aprobado"] is True
        assert result["limite"] == 500.0

    def test_rejected_over_limit(self):
        conn = _make_db()
        svc = _make_service(conn)
        result = svc.controlar_credito(1, 600.0)
        assert result["aprobado"] is False


class TestControlarAnticipo:
    def test_registers_anticipo(self):
        conn = _make_db()
        svc = _make_service(conn)
        result = svc.controlar_anticipo(1, 50.0, usuario_id=1)
        assert result["registrado"] is True
        assert result["anticipo_id"] > 0
        # Verifica asiento contable generado
        ledger = svc.obtener_ledger("caja")
        assert len(ledger) >= 1


class TestCalcularMargenReal:
    def test_basic_margin(self):
        conn = _make_db()
        svc = _make_service(conn)
        # venta_id=1: total=200, items: 2 unidades de producto_id=1 (costo=50) → costo=100
        # margen = (200-100)/200 = 0.50
        margen = svc.calcular_margen_real(1)
        assert margen == 0.50

    def test_missing_venta_returns_minus_one(self):
        conn = _make_db()
        svc = _make_service(conn)
        assert svc.calcular_margen_real(9999) == -1.0
