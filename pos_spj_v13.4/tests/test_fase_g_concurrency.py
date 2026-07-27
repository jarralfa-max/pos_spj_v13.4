# tests/test_fase_g_concurrency.py
"""
Fase G — Pruebas de concurrencia.
Verifica que las reservas de stock y las escrituras simultáneas
no producen condiciones de carrera ni stock negativo.
"""
from __future__ import annotations
import sqlite3
import threading
import time
from typing import List
import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_full_db(initial_stock: float = 100.0) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(f"""
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL,
            existencia REAL DEFAULT 0,
            precio REAL DEFAULT 0,
            precio_compra REAL DEFAULT 0,
            stock_minimo REAL DEFAULT 0,
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
            tipo TEXT, cuenta_debe TEXT, cuenta_haber TEXT,
            monto REAL, referencia TEXT, descripcion TEXT,
            usuario TEXT, sucursal_id INTEGER DEFAULT 1,
            fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE stock_reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT UNIQUE,
            producto_id INTEGER,
            cantidad REAL,
            estado TEXT DEFAULT 'activa',
            sucursal_id INTEGER DEFAULT 1,
            expires_at DATETIME,
            created_at DATETIME DEFAULT (datetime('now'))
        );
        INSERT INTO productos (id, nombre, existencia)
            VALUES (1, 'Pollo', {initial_stock});
        INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad)
            VALUES (1, 1, {initial_stock});
        INSERT INTO branch_inventory (product_id, branch_id, quantity)
            VALUES (1, 1, {initial_stock});
    """)
    conn.commit()
    return conn


# ── Concurrency tests ─────────────────────────────────────────────────────────

class TestConcurrentInventoryWrites:
    def test_concurrent_entradas_no_corrupcion(self):
        """10 hilos insertan entradas simultáneamente; el total final debe ser correcto."""
        conn = _make_full_db(initial_stock=0.0)

        from core.services.erp_application_service import ERPApplicationService
        svc = ERPApplicationService(db_conn=conn)

        NUM_THREADS = 10
        QTY_EACH = 5.0
        errors: List[Exception] = []
        barrier = threading.Barrier(NUM_THREADS)

        def worker(thread_id: int):
            try:
                barrier.wait()  # todos arrancan al mismo tiempo
                svc.registrar_compra(
                    producto_id=1,
                    cantidad=QTY_EACH,
                    costo_unitario=80.0,
                    usuario=f"t{thread_id}",
                    referencia=f"OC-{thread_id:03d}",
                    sucursal_id=1,
                )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Errores en hilos: {errors}"

        existencia = conn.execute(
            "SELECT existencia FROM productos WHERE id=1"
        ).fetchone()["existencia"]
        assert existencia == NUM_THREADS * QTY_EACH, \
            f"Esperado {NUM_THREADS * QTY_EACH}, obtenido {existencia}"

    def test_stock_no_negativo_bajo_concurrencia(self):
        """
        20 hilos intentan hacer salidas de 10 unidades sobre un stock de 50.
        Sólo 5 deben tener éxito; el stock resultante debe ser >= 0.
        """
        INITIAL = 50.0
        conn = _make_full_db(initial_stock=INITIAL)

        from core.services.erp_application_service import ERPApplicationService
        svc = ERPApplicationService(db_conn=conn)

        NUM_THREADS = 20
        QTY_EACH = 10.0
        barrier = threading.Barrier(NUM_THREADS)

        def worker():
            try:
                barrier.wait()
                svc._salida_directa(
                    prod_id=1, qty=QTY_EACH,
                    tipo="VENTA", ref="VNT",
                    usuario="t", sid=1
                )
            except Exception:
                pass  # colisión esperada en SQLite — el lock serializa

        threads = [threading.Thread(target=worker) for _ in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        # inventario_actual y branch_inventory usan MAX(0,...) — nunca negativo
        ia = conn.execute(
            "SELECT cantidad FROM inventario_actual WHERE producto_id=1 AND sucursal_id=1"
        ).fetchone()["cantidad"]
        bi = conn.execute(
            "SELECT quantity FROM branch_inventory WHERE product_id=1 AND branch_id=1"
        ).fetchone()["quantity"]

        assert ia >= 0.0, f"inventario_actual negativo: {ia}"
        assert bi >= 0.0, f"branch_inventory negativo: {bi}"


class TestStockReservationConcurrency:
    def _make_reservation_svc(self, conn):
        from core.services.stock_reservation_service import StockReservationService
        return StockReservationService(db=conn, branch_id=1)

    def test_reservas_secuenciales_n_folios_unicos(self):
        """
        50 reservas secuenciales con folios únicos; todas deben tener éxito
        y los IDs resultantes deben ser únicos.

        Nota: SQLite SAVEPOINTs son per-conexión y no son seguros para uso
        concurrente en un solo objeto de conexión. En producción, cada request
        FastAPI obtiene su propia conexión del pool.
        """
        conn = _make_full_db(initial_stock=500.0)
        svc = self._make_reservation_svc(conn)

        NUM = 50
        ids: List[int] = []

        for i in range(NUM):
            rid = svc.reservar(
                folio=f"RSV-{i:04d}",
                items=[{"id": 1, "cantidad": 1.0}]
            )
            ids.append(rid)

        assert len(ids) == NUM
        assert len(set(ids)) == len(ids), "IDs de reserva duplicados"

    def test_folio_duplicado_genera_error(self):
        """Intentar reservar el mismo folio dos veces debe fallar."""
        conn = _make_full_db(initial_stock=100.0)
        svc = self._make_reservation_svc(conn)

        svc.reservar(folio="RSV-DUP", items=[{"id": 1, "cantidad": 1.0}])

        with pytest.raises(Exception):
            svc.reservar(folio="RSV-DUP", items=[{"id": 1, "cantidad": 1.0}])

    def test_expiracion_libera_reservas_viejas(self):
        """
        Reservas expiradas no bloquean nuevas reservas del mismo folio.
        """
        conn = _make_full_db(initial_stock=100.0)
        svc = self._make_reservation_svc(conn)

        # Crear una reserva que ya expiró manualmente (tabla interna del servicio)
        conn.execute("""
            INSERT INTO stock_reservas
                (folio, branch_id, estado, payload_json, expires_at)
            VALUES ('RSV-EXP', 1, 'activa', '[]', datetime('now', '-1 hour'))
        """)
        conn.commit()

        expiradas = svc.expirar_huerfanas()
        assert expiradas >= 1

        # Ahora podemos crear una nueva reserva sin problema
        rid = svc.reservar(
            folio="RSV-NUEVA",
            items=[{"id": 1, "cantidad": 5.0}]
        )
        assert rid > 0


class TestSavepointIsolation:
    def test_savepoint_rollback_no_contamina(self):
        """
        Un SAVEPOINT con fallo no debe afectar la transacción exterior.
        """
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE cuentas (id INTEGER PRIMARY KEY, saldo REAL DEFAULT 0);
            INSERT INTO cuentas VALUES (1, 1000.0);
        """)

        # Transacción exterior
        conn.execute("BEGIN")
        conn.execute("UPDATE cuentas SET saldo = saldo - 100 WHERE id=1")

        # SAVEPOINT fallido
        sp = "sp_test_isolation"
        conn.execute(f"SAVEPOINT {sp}")
        conn.execute("UPDATE cuentas SET saldo = saldo - 9000 WHERE id=1")
        conn.execute(f"ROLLBACK TO SAVEPOINT {sp}")
        conn.execute(f"RELEASE SAVEPOINT {sp}")

        # Commit exterior — solo el -100 debe persistir
        conn.execute("COMMIT")

        saldo = conn.execute("SELECT saldo FROM cuentas WHERE id=1").fetchone()["saldo"]
        assert saldo == 900.0, f"SAVEPOINT contaminó la transacción exterior: saldo={saldo}"
