# tests/test_fase_g_inventory_integrity.py
"""
Fase G — Integridad de inventario.
Verifica que las 3 tablas de stock (productos.existencia,
inventario_actual, branch_inventory) se mantienen coherentes
después de cada operación de escritura.
"""
from __future__ import annotations
import sqlite3
import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_db() -> sqlite3.Connection:
    """Crea BD en memoria con el esquema mínimo para ERPApplicationService."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL,
            precio REAL DEFAULT 0,
            precio_compra REAL DEFAULT 0,
            existencia REAL DEFAULT 0,
            stock_minimo REAL DEFAULT 0,
            unidad TEXT DEFAULT 'pza',
            activo INTEGER DEFAULT 1
        );
        CREATE TABLE inventario_actual (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL,
            sucursal_id INTEGER DEFAULT 1,
            cantidad REAL DEFAULT 0,
            costo_promedio REAL DEFAULT 0,
            ultima_actualizacion DATETIME DEFAULT (datetime('now')),
            UNIQUE(producto_id, sucursal_id)
        );
        CREATE TABLE branch_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            branch_id INTEGER NOT NULL,
            quantity REAL DEFAULT 0,
            updated_at DATETIME DEFAULT (datetime('now')),
            UNIQUE(product_id, branch_id)
        );
        CREATE TABLE movimientos_inventario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT,
            producto_id INTEGER,
            tipo TEXT,
            tipo_movimiento TEXT,
            cantidad REAL,
            existencia_anterior REAL DEFAULT 0,
            existencia_nueva REAL DEFAULT 0,
            costo_unitario REAL DEFAULT 0,
            costo_total REAL DEFAULT 0,
            descripcion TEXT,
            referencia TEXT,
            usuario TEXT,
            sucursal_id INTEGER DEFAULT 1,
            fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE financial_event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT,
            cuenta_debe TEXT,
            cuenta_haber TEXT,
            monto REAL,
            referencia TEXT,
            descripcion TEXT,
            usuario TEXT,
            sucursal_id INTEGER DEFAULT 1,
            fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT,
            sucursal_id INTEGER DEFAULT 1,
            usuario TEXT,
            cliente_id INTEGER,
            subtotal REAL DEFAULT 0,
            descuento REAL DEFAULT 0,
            total REAL DEFAULT 0,
            forma_pago TEXT DEFAULT 'Efectivo',
            estado TEXT DEFAULT 'completada',
            notas TEXT,
            fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE detalles_venta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id INTEGER,
            producto_id INTEGER,
            nombre TEXT,
            cantidad REAL,
            precio_unitario REAL,
            descuento REAL DEFAULT 0,
            subtotal REAL
        );
        INSERT INTO productos (id, nombre, precio, precio_compra, existencia)
            VALUES (1, 'Pollo Entero', 150.0, 80.0, 0.0);
        INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad)
            VALUES (1, 1, 0.0);
        INSERT INTO branch_inventory (product_id, branch_id, quantity)
            VALUES (1, 1, 0.0);
    """)
    conn.commit()
    return conn


def _stock_snapshot(conn, producto_id: int, sucursal_id: int = 1) -> dict:
    """Lee el stock de las 3 tablas a la vez."""
    p = conn.execute(
        "SELECT existencia FROM productos WHERE id=?", (producto_id,)
    ).fetchone()
    ia = conn.execute(
        "SELECT cantidad FROM inventario_actual WHERE producto_id=? AND sucursal_id=?",
        (producto_id, sucursal_id)
    ).fetchone()
    bi = conn.execute(
        "SELECT quantity FROM branch_inventory WHERE product_id=? AND branch_id=?",
        (producto_id, sucursal_id)
    ).fetchone()
    return {
        "existencia": float(p["existencia"]) if p else None,
        "inventario_actual": float(ia["cantidad"]) if ia else None,
        "branch_inventory": float(bi["quantity"]) if bi else None,
    }


def _make_service(conn):
    from core.services.erp_application_service import ERPApplicationService
    return ERPApplicationService(db_conn=conn)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestInventoryIntegrityAfterEntrada:
    def test_tres_tablas_incrementan_juntas(self):
        conn = _make_db()
        svc = _make_service(conn)

        before = _stock_snapshot(conn, 1)
        assert before == {"existencia": 0.0, "inventario_actual": 0.0, "branch_inventory": 0.0}

        svc.registrar_compra(
            producto_id=1, cantidad=10.0, costo_unitario=80.0,
            usuario="test", referencia="OC-001", sucursal_id=1
        )

        after = _stock_snapshot(conn, 1)
        assert after["existencia"] == 10.0,        f"productos.existencia: {after}"
        assert after["inventario_actual"] == 10.0, f"inventario_actual: {after}"
        assert after["branch_inventory"] == 10.0,  f"branch_inventory: {after}"

    def test_dos_entradas_acumulan(self):
        conn = _make_db()
        svc = _make_service(conn)

        svc.registrar_compra(producto_id=1, cantidad=10.0, costo_unitario=80.0,
                             usuario="test", referencia="OC-001", sucursal_id=1)
        svc.registrar_compra(producto_id=1, cantidad=5.0, costo_unitario=85.0,
                             usuario="test", referencia="OC-002", sucursal_id=1)

        snap = _stock_snapshot(conn, 1)
        assert snap["existencia"] == 15.0
        assert snap["inventario_actual"] == 15.0
        assert snap["branch_inventory"] == 15.0

    def test_movimiento_registrado(self):
        conn = _make_db()
        svc = _make_service(conn)

        svc.registrar_compra(producto_id=1, cantidad=7.5, costo_unitario=80.0,
                             usuario="test", referencia="OC-003", sucursal_id=1)

        count = conn.execute(
            "SELECT COUNT(*) FROM movimientos_inventario WHERE producto_id=1 AND tipo='ENTRADA'"
        ).fetchone()[0]
        assert count == 1


class TestInventoryIntegrityAfterAjuste:
    def test_ajuste_sincroniza_tres_tablas(self):
        conn = _make_db()
        svc = _make_service(conn)

        # Seed stock
        svc.registrar_compra(producto_id=1, cantidad=20.0, costo_unitario=80.0,
                             usuario="test", referencia="init", sucursal_id=1)

        svc.registrar_ajuste(
            producto_id=1, nueva_cantidad=15.0,
            motivo="merma prueba", usuario="test", sucursal_id=1
        )

        snap = _stock_snapshot(conn, 1)
        assert snap["existencia"] == 15.0,        f"productos.existencia: {snap}"
        assert snap["inventario_actual"] == 15.0, f"inventario_actual: {snap}"
        assert snap["branch_inventory"] == 15.0,  f"branch_inventory: {snap}"

    def test_ajuste_a_cero(self):
        conn = _make_db()
        svc = _make_service(conn)

        svc.registrar_compra(producto_id=1, cantidad=10.0, costo_unitario=80.0,
                             usuario="test", referencia="init", sucursal_id=1)
        svc.registrar_ajuste(
            producto_id=1, nueva_cantidad=0.0,
            motivo="conteo físico", usuario="test", sucursal_id=1
        )

        snap = _stock_snapshot(conn, 1)
        assert snap["existencia"] == 0.0
        assert snap["inventario_actual"] == 0.0
        assert snap["branch_inventory"] == 0.0


class TestInventoryIntegrityAfterSalida:
    def test_salida_resta_en_tres_tablas(self):
        conn = _make_db()
        svc = _make_service(conn)

        svc.registrar_compra(producto_id=1, cantidad=20.0, costo_unitario=80.0,
                             usuario="test", referencia="init", sucursal_id=1)

        # Llamar _salida_directa directamente (es método privado usado por anular_venta, etc.)
        svc._salida_directa(
            prod_id=1, qty=6.0,
            tipo="VENTA", ref="VNT-001",
            usuario="test", sid=1
        )

        snap = _stock_snapshot(conn, 1)
        assert snap["existencia"] == 14.0
        assert snap["inventario_actual"] == 14.0
        assert snap["branch_inventory"] == 14.0

    def test_salida_no_va_negativo(self):
        """Stock nunca cae por debajo de 0."""
        conn = _make_db()
        svc = _make_service(conn)

        svc.registrar_compra(producto_id=1, cantidad=5.0, costo_unitario=80.0,
                             usuario="test", referencia="init", sucursal_id=1)
        svc._salida_directa(
            prod_id=1, qty=99.0, tipo="VENTA",
            ref="VNT-OVERFLOW", usuario="test", sid=1
        )

        snap = _stock_snapshot(conn, 1)
        # inventario_actual y branch_inventory usan MAX(0, ...)
        assert snap["inventario_actual"] >= 0.0
        assert snap["branch_inventory"] >= 0.0


class TestInventoryCoherence:
    def test_tablas_siempre_coinciden_tras_n_ops(self):
        """Realiza N operaciones mixtas y verifica coherencia al final."""
        conn = _make_db()
        svc = _make_service(conn)

        ops = [
            ("compra", 50.0, 80.0),
            ("compra", 30.0, 82.0),
            ("salida", 10.0, 0),
            ("ajuste", 60.0, 0),
            ("salida", 5.0, 0),
            ("compra", 20.0, 79.0),
        ]

        for op, qty, costo in ops:
            if op == "compra":
                svc.registrar_compra(producto_id=1, cantidad=qty,
                                     costo_unitario=costo,
                                     usuario="test", referencia="X",
                                     sucursal_id=1)
            elif op == "salida":
                svc._salida_directa(prod_id=1, qty=qty,
                                    tipo="VENTA", ref="X",
                                    usuario="test", sid=1)
            elif op == "ajuste":
                svc.registrar_ajuste(producto_id=1, nueva_cantidad=qty,
                                     motivo="test", usuario="test",
                                     sucursal_id=1)

        snap = _stock_snapshot(conn, 1)
        assert snap["existencia"] == snap["inventario_actual"], \
            f"existencia vs inventario_actual diverge: {snap}"
        assert snap["inventario_actual"] == snap["branch_inventory"], \
            f"inventario_actual vs branch_inventory diverge: {snap}"

    def test_costo_promedio_ponderado(self):
        """Verifica cálculo de costo promedio ponderado en inventario_actual."""
        conn = _make_db()
        svc = _make_service(conn)

        svc.registrar_compra(producto_id=1, cantidad=10.0, costo_unitario=80.0,
                             usuario="test", referencia="c1", sucursal_id=1)
        svc.registrar_compra(producto_id=1, cantidad=10.0, costo_unitario=100.0,
                             usuario="test", referencia="c2", sucursal_id=1)

        row = conn.execute(
            "SELECT costo_promedio FROM inventario_actual WHERE producto_id=1 AND sucursal_id=1"
        ).fetchone()
        costo_prom = float(row["costo_promedio"])
        # 10*80 + 10*100 = 1800 / 20 = 90
        assert abs(costo_prom - 90.0) < 0.01, f"Costo promedio esperado 90, obtenido {costo_prom}"
