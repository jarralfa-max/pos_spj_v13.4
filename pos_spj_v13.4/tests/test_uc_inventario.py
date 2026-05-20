# tests/test_uc_inventario.py — SPJ POS v13.4
"""Tests para GestionarInventarioUC (core/use_cases/inventario.py)."""
import sys
import os
import sqlite3
import pytest
from unittest.mock import MagicMock, call

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers / fakes
# ─────────────────────────────────────────────────────────────────────────────

class _FakeInventoryService:
    """Minimal in-memory inventory service for UC tests."""

    def __init__(self, initial_stock: float = 100.0):
        self._stock: dict = {}  # (product_id, branch_id) -> float
        self._default = initial_stock
        self.movements: list = []

    def _key(self, pid, bid):
        return (pid, bid)

    def get_stock(self, product_id: int, branch_id: int) -> float:
        return self._stock.get(self._key(product_id, branch_id), self._default)

    def add_stock(self, product_id, branch_id, qty, **kw):
        k = self._key(product_id, branch_id)
        self._stock[k] = self._stock.get(k, self._default) + qty
        self.movements.append(("ADD", product_id, branch_id, qty))

    def deduct_stock(self, product_id, branch_id, qty, **kw):
        k = self._key(product_id, branch_id)
        self._stock[k] = self._stock.get(k, self._default) - qty
        self.movements.append(("DEDUCT", product_id, branch_id, qty))


def _make_db():
    """In-memory DB with minimal schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            accion TEXT, modulo TEXT, entidad TEXT, entidad_id INTEGER,
            usuario TEXT, sucursal_id INTEGER,
            valor_antes TEXT, valor_despues TEXT, detalles TEXT,
            fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE sync_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT UNIQUE, tabla TEXT, operacion TEXT, registro_id INTEGER,
            payload TEXT, sucursal_id INTEGER DEFAULT 1,
            lamport_ts INTEGER DEFAULT 0, synced INTEGER DEFAULT 0,
            fecha DATETIME DEFAULT (datetime('now'))
        );
    """)
    return conn


def _make_uc(initial_stock=100.0, event_bus=None):
    from core.use_cases.inventario import GestionarInventarioUC
    inv = _FakeInventoryService(initial_stock)
    db = _make_db()
    uc = GestionarInventarioUC(db=db, inventory_service=inv, event_bus=event_bus)
    return uc, inv, db


# ─────────────────────────────────────────────────────────────────────────────
# registrar_entrada
# ─────────────────────────────────────────────────────────────────────────────

class TestRegistrarEntrada:
    def test_entrada_ok_retorna_resultado_positivo(self):
        uc, inv, _ = _make_uc(initial_stock=50.0)
        r = uc.registrar_entrada(
            producto_id=1, cantidad=20.0, sucursal_id=1, usuario="almacen"
        )
        assert r.ok is True
        assert r.operacion_id.startswith("INV-")
        assert r.stock_nuevo == pytest.approx(70.0)

    def test_entrada_incrementa_stock(self):
        uc, inv, _ = _make_uc(initial_stock=0.0)
        inv._stock[(1, 1)] = 30.0
        uc.registrar_entrada(producto_id=1, cantidad=10.0, sucursal_id=1, usuario="x")
        assert inv.get_stock(1, 1) == pytest.approx(40.0)

    def test_entrada_cantidad_cero_retorna_error(self):
        uc, _, _ = _make_uc()
        r = uc.registrar_entrada(producto_id=1, cantidad=0.0, sucursal_id=1, usuario="x")
        assert r.ok is False
        assert "0" in r.error or "Cantidad" in r.error

    def test_entrada_cantidad_negativa_retorna_error(self):
        uc, _, _ = _make_uc()
        r = uc.registrar_entrada(producto_id=1, cantidad=-5.0, sucursal_id=1, usuario="x")
        assert r.ok is False

    def test_entrada_publica_evento_ajuste_inventario(self):
        bus = MagicMock()
        uc, _, _ = _make_uc(event_bus=bus)
        uc.registrar_entrada(producto_id=3, cantidad=5.0, sucursal_id=1, usuario="y")
        bus.publish.assert_called_once()
        args = bus.publish.call_args
        event_name = args.args[0] if args.args else args[0][0]
        assert event_name == "AJUSTE_INVENTARIO"

    def test_entrada_escribe_audit_log(self):
        uc, _, db = _make_uc()
        uc.registrar_entrada(producto_id=2, cantidad=15.0, sucursal_id=1, usuario="test")
        rows = db.execute("SELECT * FROM audit_logs WHERE entidad='productos'").fetchall()
        assert len(rows) >= 1

    def test_entrada_fallo_servicio_retorna_error(self):
        from core.use_cases.inventario import GestionarInventarioUC
        inv = MagicMock()
        inv.get_stock.side_effect = RuntimeError("DB down")
        uc = GestionarInventarioUC(db=_make_db(), inventory_service=inv)
        r = uc.registrar_entrada(producto_id=1, cantidad=5.0, sucursal_id=1, usuario="x")
        assert r.ok is False
        assert "DB down" in r.error


# ─────────────────────────────────────────────────────────────────────────────
# registrar_ajuste
# ─────────────────────────────────────────────────────────────────────────────

class TestRegistrarAjuste:
    def test_ajuste_positivo_incrementa_stock(self):
        uc, inv, _ = _make_uc(initial_stock=0.0)
        inv._stock[(1, 1)] = 30.0
        r = uc.registrar_ajuste(
            producto_id=1, cantidad_nueva=50.0, sucursal_id=1, usuario="mgr"
        )
        assert r.ok is True
        assert r.stock_nuevo == pytest.approx(50.0)

    def test_ajuste_negativo_reduce_stock(self):
        uc, inv, _ = _make_uc(initial_stock=0.0)
        inv._stock[(1, 1)] = 80.0
        r = uc.registrar_ajuste(
            producto_id=1, cantidad_nueva=40.0, sucursal_id=1, usuario="mgr"
        )
        assert r.ok is True
        assert r.stock_nuevo == pytest.approx(40.0)

    def test_ajuste_sin_cambio_no_falla(self):
        uc, inv, _ = _make_uc(initial_stock=0.0)
        inv._stock[(1, 1)] = 50.0
        r = uc.registrar_ajuste(
            producto_id=1, cantidad_nueva=50.0, sucursal_id=1, usuario="mgr"
        )
        assert r.ok is True

    def test_ajuste_publica_evento(self):
        bus = MagicMock()
        uc, inv, _ = _make_uc(initial_stock=0.0, event_bus=bus)
        inv._stock[(1, 1)] = 20.0
        uc.registrar_ajuste(producto_id=1, cantidad_nueva=30.0, sucursal_id=1, usuario="x")
        bus.publish.assert_called_once()

    def test_ajuste_operacion_id_retornado(self):
        uc, inv, _ = _make_uc(initial_stock=0.0)
        inv._stock[(2, 1)] = 10.0
        r = uc.registrar_ajuste(
            producto_id=2, cantidad_nueva=12.0, sucursal_id=1, usuario="admin"
        )
        assert r.operacion_id.startswith("INV-")


# ─────────────────────────────────────────────────────────────────────────────
# registrar_traspaso
# ─────────────────────────────────────────────────────────────────────────────

class TestRegistrarTraspaso:
    def test_traspaso_valido_descuenta_origen_y_suma_destino(self):
        uc, inv, _ = _make_uc(initial_stock=0.0)
        inv._stock[(5, 1)] = 60.0
        inv._stock[(5, 2)] = 10.0
        r = uc.registrar_traspaso(
            producto_id=5, cantidad=20.0,
            sucursal_origen=1, sucursal_destino=2,
            usuario="almacen",
        )
        assert r.ok is True
        assert inv.get_stock(5, 1) == pytest.approx(40.0)
        assert inv.get_stock(5, 2) == pytest.approx(30.0)

    def test_traspaso_mismo_origen_destino_retorna_error(self):
        uc, _, _ = _make_uc()
        r = uc.registrar_traspaso(
            producto_id=1, cantidad=10.0,
            sucursal_origen=1, sucursal_destino=1,
            usuario="x",
        )
        assert r.ok is False
        assert "Origen" in r.error or "destino" in r.error.lower()

    def test_traspaso_cantidad_cero_retorna_error(self):
        uc, _, _ = _make_uc()
        r = uc.registrar_traspaso(
            producto_id=1, cantidad=0.0,
            sucursal_origen=1, sucursal_destino=2,
            usuario="x",
        )
        assert r.ok is False

    def test_traspaso_publica_evento_traspaso_iniciado(self):
        bus = MagicMock()
        uc, inv, _ = _make_uc(initial_stock=0.0, event_bus=bus)
        inv._stock[(3, 1)] = 50.0
        inv._stock[(3, 2)] = 0.0
        uc.registrar_traspaso(
            producto_id=3, cantidad=10.0,
            sucursal_origen=1, sucursal_destino=2,
            usuario="mgr",
        )
        bus.publish.assert_called_once()
        event_name = bus.publish.call_args.args[0]
        assert event_name == "TRASPASO_INICIADO"

    def test_traspaso_fallo_retorna_error(self):
        from core.use_cases.inventario import GestionarInventarioUC
        inv = MagicMock()
        inv.get_stock.return_value = 100.0
        inv.deduct_stock.side_effect = RuntimeError("stock insuficiente")
        uc = GestionarInventarioUC(db=_make_db(), inventory_service=inv)
        r = uc.registrar_traspaso(
            producto_id=1, cantidad=10.0,
            sucursal_origen=1, sucursal_destino=2,
            usuario="x",
        )
        assert r.ok is False
        assert "stock insuficiente" in r.error
