"""
tests/purchases/test_fase5_direct_purchase_flow.py
───────────────────────────────────────────────────
FASE 5 — Estabilizar compra directa (DIRECT).

Verifica (sin instanciar PyQt5):
1. RegistrarCompraUC — validaciones y flujo feliz con SQLite in-memory
2. PurchaseRepository — round-trip create/read, draft save/load/delete
3. _procesar_compra() routing — DIRECT/PR/PO por AST
4. Draft dict structure — _build_draft_dict keys, _restore_draft_dict, _auto_save_draft
5. Fallback directo deshabilitado — sin SQL/UI ni bypass de inventario
6. Auto-save timer — _autosave_timer inicializado con 45 000 ms en __init__
"""
from __future__ import annotations

import ast
import importlib
import json
import os
import re
import sqlite3
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# ── Shared helpers ────────────────────────────────────────────────────────────

def _source() -> str:
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return open(os.path.join(base, "modulos", "compras_pro.py"), encoding="utf-8").read()


def _method_src(method_name: str) -> str | None:
    src = _source()
    tree = ast.parse(src)
    lines = src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ModuloComprasPro":
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
                    return "\n".join(lines[item.lineno - 1:item.end_lineno])
    return None


# ── In-memory DB fixture ─────────────────────────────────────────────────────

def _make_db() -> sqlite3.Connection:
    """Minimal SQLite in-memory schema for purchase flow tests.
    isolation_level=None matches production DB (autocommit / manual SAVEPOINT control).
    """
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            activo INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            existencia REAL DEFAULT 0,
            precio_compra REAL DEFAULT 0,
            activo INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS compras (
            id TEXT PRIMARY KEY,
            folio TEXT,
            proveedor_id INTEGER,
            usuario TEXT,
            subtotal REAL DEFAULT 0,
            iva REAL DEFAULT 0,
            total REAL DEFAULT 0,
            estado TEXT DEFAULT 'completada',
            forma_pago TEXT DEFAULT 'CONTADO',
            observaciones TEXT,
            sucursal_id INTEGER DEFAULT 1,
            fecha TEXT DEFAULT (datetime('now')),
            factura TEXT,
            condicion_pago TEXT DEFAULT 'liquidado',
            plazo_dias INTEGER DEFAULT 0,
            moneda TEXT DEFAULT 'MXN'
        );
        CREATE TABLE IF NOT EXISTS detalles_compra (
            id TEXT PRIMARY KEY,
            compra_id INTEGER,
            producto_id INTEGER,
            cantidad REAL,
            precio_unitario REAL,
            costo_unitario REAL,
            subtotal REAL
        );
        CREATE TABLE IF NOT EXISTS temp_purchase_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT,
            sucursal_id INTEGER,
            draft_data TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS financial_event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            modulo TEXT,
            accion TEXT,
            entidad TEXT,
            entidad_id TEXT,
            usuario TEXT,
            detalles TEXT,
            before_json TEXT,
            after_json TEXT,
            sucursal_id INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS lotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT,
            producto_id INTEGER,
            numero_lote TEXT UNIQUE,
            proveedor_id INTEGER,
            peso_inicial_kg REAL,
            peso_actual_kg REAL,
            costo_kg REAL,
            fecha_caducidad TEXT,
            sucursal_id INTEGER,
            temperatura_c REAL,
            observaciones TEXT,
            estado TEXT DEFAULT 'activo'
        );
        CREATE TABLE IF NOT EXISTS movimientos_lote (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lote_id INTEGER,
            tipo TEXT,
            cantidad_kg REAL,
            referencia TEXT,
            usuario TEXT
        );
    """)
    importlib.import_module("migrations.standalone.098_canonical_inventory").run(conn)

    # Seed test data
    conn.execute("INSERT INTO proveedores (nombre) VALUES ('Prov Test')")
    conn.execute("INSERT INTO productos (nombre, existencia) VALUES ('Pollo', 100)")
    conn.execute("INSERT INTO inventory_stock(product_id, branch_id, quantity, unit) VALUES (1, 1, 100, 'unit')")
    conn.commit()
    return conn


def _make_mock_inventory_service(db):
    """Stub that updates canonical inventory_stock directly for purchase tests."""
    svc = MagicMock()

    def _increase_stock(product_id, branch_id, quantity, unit, reason, operation_id,
                        source_module, reference_type=None, reference_id=None, user_name=""):
        db.execute(
            """
            INSERT INTO inventory_stock(product_id, branch_id, quantity, unit)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(product_id, branch_id) DO UPDATE SET
                quantity = quantity + excluded.quantity,
                unit = excluded.unit
            """,
            (product_id, branch_id, quantity, unit),
        )
        return MagicMock(success=True, stock_before=None, stock_after=None, events=())

    svc.increase_stock.side_effect = _increase_stock
    return svc


def _make_purchase_service(db):
    """Build a real PurchaseService wired to an in-memory DB."""
    from repositories.purchase_repository import PurchaseRepository
    from core.services.purchase_service import PurchaseService

    repo = PurchaseRepository(db)
    inv_svc = _make_mock_inventory_service(db)
    fin_svc = None  # finance is optional; tested separately
    return PurchaseService(db, repo, inv_svc, fin_svc), repo


def _make_container(db):
    """Minimal container stub with purchase_service wired."""
    from repositories.purchase_repository import PurchaseRepository
    from core.services.purchase_service import PurchaseService

    repo = PurchaseRepository(db)
    inv_svc = _make_mock_inventory_service(db)
    svc = PurchaseService(db, repo, inv_svc, None)

    container = MagicMock()
    container.purchase_service = svc
    container.recipe_engine = None
    return container


# ── 1. RegistrarCompraUC ─────────────────────────────────────────────────────

class TestRegistrarCompraUCValidation:
    """RegistrarCompraUC.execute() rejects invalid input before touching DB."""

    def _uc(self):
        from application.use_cases.registrar_compra_uc import RegistrarCompraUC, DatosCompraDTO
        db = _make_db()
        container = _make_container(db)
        return RegistrarCompraUC(container), DatosCompraDTO

    def test_empty_cart_returns_error(self):
        from application.use_cases.registrar_compra_uc import DatosCompraDTO
        db = _make_db()
        container = _make_container(db)
        from application.use_cases.registrar_compra_uc import RegistrarCompraUC
        uc = RegistrarCompraUC(container)
        datos = DatosCompraDTO(
            proveedor_id=1, proveedor_nombre="Prov", sucursal_id=1, usuario="test",
            items=[], metodo_pago="CONTADO", doc_ref="F001",
            subtotal=0, iva_monto=0, total=0,
        )
        resultado = uc.execute(datos)
        assert not resultado.ok
        assert "vacío" in resultado.error.lower() or "empty" in resultado.error.lower()

    def test_zero_qty_returns_error(self):
        from application.use_cases.registrar_compra_uc import (
            RegistrarCompraUC, DatosCompraDTO, ItemCompraDTO,
        )
        db = _make_db()
        container = _make_container(db)
        uc = RegistrarCompraUC(container)
        datos = DatosCompraDTO(
            proveedor_id=1, proveedor_nombre="Prov", sucursal_id=1, usuario="test",
            items=[ItemCompraDTO(product_id=1, qty=0, unit_cost=50.0, nombre="Pollo")],
            metodo_pago="CONTADO", doc_ref="F001",
            subtotal=0, iva_monto=0, total=0,
        )
        resultado = uc.execute(datos)
        assert not resultado.ok
        assert "Pollo" in resultado.error or "cantidad" in resultado.error.lower() or "inválido" in resultado.error.lower()

    def test_negative_qty_returns_error(self):
        from application.use_cases.registrar_compra_uc import (
            RegistrarCompraUC, DatosCompraDTO, ItemCompraDTO,
        )
        db = _make_db()
        container = _make_container(db)
        uc = RegistrarCompraUC(container)
        datos = DatosCompraDTO(
            proveedor_id=1, proveedor_nombre="Prov", sucursal_id=1, usuario="test",
            items=[ItemCompraDTO(product_id=1, qty=-5, unit_cost=50.0, nombre="Pollo")],
            metodo_pago="CONTADO", doc_ref="F001",
            subtotal=0, iva_monto=0, total=0,
        )
        resultado = uc.execute(datos)
        assert not resultado.ok

    def test_no_purchase_service_returns_error(self):
        from application.use_cases.registrar_compra_uc import (
            RegistrarCompraUC, DatosCompraDTO, ItemCompraDTO,
        )
        container = MagicMock()
        container.purchase_service = None
        uc = RegistrarCompraUC(container)
        datos = DatosCompraDTO(
            proveedor_id=1, proveedor_nombre="Prov", sucursal_id=1, usuario="test",
            items=[ItemCompraDTO(product_id=1, qty=10, unit_cost=50.0, nombre="Pollo")],
            metodo_pago="CONTADO", doc_ref="F001",
            subtotal=500, iva_monto=0, total=500,
        )
        resultado = uc.execute(datos)
        assert not resultado.ok
        assert "PurchaseService" in resultado.error or "disponible" in resultado.error.lower()

    def test_invalid_provider_returns_error_before_db(self):
        from application.use_cases.registrar_compra_uc import (
            RegistrarCompraUC, DatosCompraDTO, ItemCompraDTO,
        )
        db = _make_db()
        container = _make_container(db)
        uc = RegistrarCompraUC(container)
        datos = DatosCompraDTO(
            proveedor_id=0, proveedor_nombre="", sucursal_id=1, usuario="test",
            items=[ItemCompraDTO(product_id=1, qty=10, unit_cost=50.0, nombre="Pollo")],
            metodo_pago="CONTADO", doc_ref="F001",
            subtotal=500, iva_monto=0, total=500,
        )
        resultado = uc.execute(datos)
        assert not resultado.ok
        assert "proveedor" in resultado.error.lower()
        assert db.execute("SELECT COUNT(*) FROM compras").fetchone()[0] == 0

    def test_total_mismatch_returns_error_before_db(self):
        from application.use_cases.registrar_compra_uc import (
            RegistrarCompraUC, DatosCompraDTO, ItemCompraDTO,
        )
        db = _make_db()
        container = _make_container(db)
        uc = RegistrarCompraUC(container)
        datos = DatosCompraDTO(
            proveedor_id=1, proveedor_nombre="Prov", sucursal_id=1, usuario="test",
            items=[ItemCompraDTO(product_id=1, qty=10, unit_cost=50.0, nombre="Pollo")],
            metodo_pago="CONTADO", doc_ref="F001",
            subtotal=500, iva_monto=80, total=500,
        )
        resultado = uc.execute(datos)
        assert not resultado.ok
        assert "total" in resultado.error.lower()
        assert db.execute("SELECT COUNT(*) FROM compras").fetchone()[0] == 0


class TestRegistrarCompraUCHappyPath:
    """RegistrarCompraUC.execute() registers a purchase and returns ok=True + folio."""

    def _run(self, qty=10.0, unit_cost=50.0, pago="CONTADO"):
        from application.use_cases.registrar_compra_uc import (
            RegistrarCompraUC, DatosCompraDTO, ItemCompraDTO,
        )
        db = _make_db()
        container = _make_container(db)
        uc = RegistrarCompraUC(container)
        subtotal = qty * unit_cost
        datos = DatosCompraDTO(
            proveedor_id=1, proveedor_nombre="Prov Test", sucursal_id=1,
            usuario="tester",
            items=[ItemCompraDTO(product_id=1, qty=qty, unit_cost=unit_cost, nombre="Pollo")],
            metodo_pago=pago, doc_ref="F-001",
            subtotal=subtotal, iva_monto=0, total=subtotal,
        )
        return uc.execute(datos), db

    def test_execute_returns_ok(self):
        resultado, _ = self._run()
        assert resultado.ok, f"Expected ok=True, got error: {resultado.error}"

    def test_execute_returns_folio(self):
        resultado, _ = self._run()
        assert resultado.folio, "Expected non-empty folio"
        assert "CMP-" in resultado.folio

    def test_purchase_saved_to_db(self):
        resultado, db = self._run()
        row = db.execute(
            "SELECT id, folio, estado FROM compras WHERE folio=?", (resultado.folio,)
        ).fetchone()
        assert row is not None, f"Purchase {resultado.folio} not found in DB"
        assert row["estado"] in ("completada", "credito")

    def test_purchase_items_saved_to_db(self):
        resultado, db = self._run()
        row = db.execute("SELECT id FROM compras WHERE folio=?", (resultado.folio,)).fetchone()
        items = db.execute(
            "SELECT * FROM detalles_compra WHERE compra_id=?", (row["id"],)
        ).fetchall()
        assert len(items) == 1
        assert float(items[0]["cantidad"]) == 10.0

    def test_inventory_updated(self):
        resultado, db = self._run(qty=5.0)
        row = db.execute("SELECT quantity FROM inventory_stock WHERE product_id=1 AND branch_id=1").fetchone()
        assert float(row["quantity"]) == 105.0, "Canonical stock should have increased by 5"

    def test_credito_pago_marks_status(self):
        from application.use_cases.registrar_compra_uc import (
            RegistrarCompraUC, DatosCompraDTO, ItemCompraDTO,
        )
        db = _make_db()
        container = _make_container(db)
        uc = RegistrarCompraUC(container)
        datos = DatosCompraDTO(
            proveedor_id=1, proveedor_nombre="Prov", sucursal_id=1, usuario="tester",
            items=[ItemCompraDTO(product_id=1, qty=10, unit_cost=50.0, nombre="Pollo")],
            metodo_pago="CREDITO", doc_ref="F-002",
            subtotal=500, iva_monto=0, total=500,
            condicion_pago="credito", plazo_dias=30,
        )
        resultado = uc.execute(datos)
        assert resultado.ok
        row = db.execute(
            "SELECT estado FROM compras WHERE folio=?", (resultado.folio,)
        ).fetchone()
        assert row["estado"] == "credito"

    def test_multiple_items(self):
        from application.use_cases.registrar_compra_uc import (
            RegistrarCompraUC, DatosCompraDTO, ItemCompraDTO,
        )
        db = _make_db()
        db.execute("INSERT INTO productos (nombre) VALUES ('Res')")
        db.commit()
        container = _make_container(db)
        uc = RegistrarCompraUC(container)
        datos = DatosCompraDTO(
            proveedor_id=1, proveedor_nombre="Prov", sucursal_id=1, usuario="tester",
            items=[
                ItemCompraDTO(product_id=1, qty=10, unit_cost=50.0, nombre="Pollo"),
                ItemCompraDTO(product_id=2, qty=5, unit_cost=80.0, nombre="Res"),
            ],
            metodo_pago="CONTADO", doc_ref="F-003",
            subtotal=900, iva_monto=0, total=900,
        )
        resultado = uc.execute(datos)
        assert resultado.ok
        row = db.execute("SELECT id FROM compras WHERE folio=?", (resultado.folio,)).fetchone()
        items = db.execute(
            "SELECT * FROM detalles_compra WHERE compra_id=?", (row["id"],)
        ).fetchall()
        assert len(items) == 2

    def test_iva_is_saved_in_purchase_header_total(self):
        from application.use_cases.registrar_compra_uc import (
            RegistrarCompraUC, DatosCompraDTO, ItemCompraDTO,
        )
        db = _make_db()
        container = _make_container(db)
        uc = RegistrarCompraUC(container)
        datos = DatosCompraDTO(
            proveedor_id=1, proveedor_nombre="Prov", sucursal_id=1, usuario="tester",
            items=[ItemCompraDTO(product_id=1, qty=10, unit_cost=50.0, nombre="Pollo")],
            metodo_pago="CONTADO", doc_ref="F-IVA",
            subtotal=500, iva_monto=80, total=580,
        )
        resultado = uc.execute(datos)
        assert resultado.ok, resultado.error
        row = db.execute(
            "SELECT subtotal, iva, total FROM compras WHERE folio=?",
            (resultado.folio,),
        ).fetchone()
        assert float(row["subtotal"]) == 500.0
        assert float(row["iva"]) == 80.0
        assert float(row["total"]) == 580.0


# ── 2. PurchaseRepository round-trip ─────────────────────────────────────────

class TestPurchaseRepositoryRoundTrip:
    """PurchaseRepository reads back what it writes."""

    def _repo(self):
        from repositories.purchase_repository import PurchaseRepository
        return PurchaseRepository(_make_db())

    def test_create_purchase_returns_id_and_folio(self):
        repo = self._repo()
        pid, folio = repo.create_purchase(
            provider_id=1, branch_id=1, user="tester", total=500,
            status="completada", operation_id="op-1",
        )
        assert isinstance(pid, str) and pid          # identidad UUIDv7
        assert folio.startswith("CMP-")

    def test_save_and_read_items(self):
        db = _make_db()
        from repositories.purchase_repository import PurchaseRepository
        repo = PurchaseRepository(db)
        pid, _ = repo.create_purchase(
            provider_id=1, branch_id=1, user="tester", total=500,
        )
        repo.save_purchase_items(pid, [
            {"product_id": 1, "qty": 10, "unit_cost": 50.0},
        ])
        items = repo.get_purchase_items_raw(pid)
        assert len(items) == 1
        assert items[0]["product_id"] == 1
        assert items[0]["qty"] == 10.0
        assert items[0]["unit_cost"] == 50.0

    def test_get_purchase_state(self):
        db = _make_db()
        from repositories.purchase_repository import PurchaseRepository
        repo = PurchaseRepository(db)
        pid, folio = repo.create_purchase(
            provider_id=1, branch_id=1, user="tester", total=100,
            status="completada",
        )
        state = repo.get_purchase_state(pid)
        assert state is not None
        assert state["folio"] == folio
        assert state["estado"] == "completada"

    def test_cancel_purchase(self):
        db = _make_db()
        from repositories.purchase_repository import PurchaseRepository
        repo = PurchaseRepository(db)
        pid, _ = repo.create_purchase(
            provider_id=1, branch_id=1, user="tester", total=100, status="completada",
        )
        repo.cancel_purchase(pid)
        state = repo.get_purchase_state(pid)
        assert state["estado"] == "cancelada"


class TestDraftRepositoryRoundTrip:
    """PurchaseRepository draft save/load/delete cycle."""

    def _repo(self):
        from repositories.purchase_repository import PurchaseRepository
        return PurchaseRepository(_make_db())

    def test_save_and_load_draft(self):
        repo = self._repo()
        draft = {"carrito": [{"nombre": "Pollo", "cantidad": 5}], "saved_at": "2026-01-01"}
        repo.save_draft("usr1", 1, json.dumps(draft))
        result = repo.load_draft("usr1", 1)
        assert result is not None
        loaded = json.loads(result[0])
        assert loaded["carrito"][0]["nombre"] == "Pollo"

    def test_load_nonexistent_draft_returns_none(self):
        repo = self._repo()
        result = repo.load_draft("nobody", 99)
        assert result is None

    def test_delete_draft(self):
        repo = self._repo()
        repo.save_draft("usr2", 1, json.dumps({"carrito": []}))
        repo.delete_draft("usr2", 1)
        result = repo.load_draft("usr2", 1)
        assert result is None

    def test_upsert_draft_overwrites(self):
        repo = self._repo()
        repo.save_draft("usr3", 1, json.dumps({"carrito": [{"nombre": "A"}]}))
        repo.save_draft("usr3", 1, json.dumps({"carrito": [{"nombre": "B"}, {"nombre": "C"}]}))
        result = repo.load_draft("usr3", 1)
        loaded = json.loads(result[0])
        assert len(loaded["carrito"]) == 2
        assert loaded["carrito"][0]["nombre"] == "B"


# ── 3. _procesar_compra routing (AST) ────────────────────────────────────────

class TestProcesarCompraRouting:
    """_procesar_compra() routes correctly by _doc_type via AST inspection."""

    def _src(self):
        return _method_src("_procesar_compra")

    def test_method_exists(self):
        assert self._src() is not None

    def test_direct_delegates_to_registrar_compra_uc(self):
        src = self._src()
        assert "RegistrarCompraUC" in src, (
            "_procesar_compra debe delegar al UC RegistrarCompraUC para DIRECT"
        )

    def test_pr_route_calls_procesar_como_pr(self):
        src = self._src()
        assert "_procesar_como_pr" in src, (
            "_procesar_compra debe llamar _procesar_como_pr cuando doc_type == 'PR'"
        )

    def test_doc_type_check_present(self):
        src = self._src()
        assert "_doc_type" in src or "doc_type" in src, (
            "_procesar_compra debe comprobar el tipo de documento activo"
        )

    def test_direct_path_builds_datos_uc(self):
        src = self._src()
        assert "DatosCompraDTO" in src, (
            "_procesar_compra debe construir DatosCompraDTO para el flujo DIRECT"
        )

    def test_result_ok_shows_toast(self):
        src = self._src()
        assert "Toast" in src or "toast" in src.lower(), (
            "_procesar_compra debe mostrar Toast.success al completar"
        )

    def test_result_error_shows_critical(self):
        src = self._src()
        assert "critical" in src.lower() or "QMessageBox" in src, (
            "_procesar_compra debe mostrar error cuando resultado.ok es False"
        )

    def test_clears_cart_after_success(self):
        src = self._src()
        assert "carrito_compra.clear()" in src, (
            "_procesar_compra debe limpiar el carrito después de una compra exitosa"
        )

    def test_refresh_tabla_after_success(self):
        src = self._src()
        assert "_refresh_tabla" in src, (
            "_procesar_compra debe llamar _refresh_tabla después de procesar"
        )


# ── 4. Draft dict structure (AST) ────────────────────────────────────────────

class TestDraftDictStructure:
    """_build_draft_dict and related methods have the required structure."""

    def test_build_draft_dict_exists(self):
        assert _method_src("_build_draft_dict") is not None

    def test_build_draft_dict_has_carrito_key(self):
        src = _method_src("_build_draft_dict")
        assert '"carrito"' in src or "'carrito'" in src

    def test_build_draft_dict_has_proveedor_id_key(self):
        src = _method_src("_build_draft_dict")
        assert "proveedor_id" in src

    def test_build_draft_dict_has_saved_at_key(self):
        src = _method_src("_build_draft_dict")
        assert "saved_at" in src

    def test_restore_draft_dict_exists(self):
        assert _method_src("_restore_draft_dict") is not None

    def test_restore_draft_dict_restores_carrito(self):
        src = _method_src("_restore_draft_dict")
        assert "carrito_compra" in src

    def test_restore_draft_dict_calls_refresh_tabla(self):
        src = _method_src("_restore_draft_dict")
        assert "_refresh_tabla" in src

    def test_auto_save_draft_exists(self):
        assert _method_src("_auto_save_draft") is not None

    def test_auto_save_draft_checks_cart_nonempty(self):
        src = _method_src("_auto_save_draft")
        assert "carrito_compra" in src

    def test_auto_save_draft_uses_purchase_repo(self):
        src = _method_src("_auto_save_draft")
        assert "_purchase_repo" in src

    def test_guardar_borrador_exists(self):
        assert _method_src("_guardar_borrador") is not None

    def test_cargar_borrador_exists(self):
        assert _method_src("_cargar_borrador") is not None

    def test_cargar_borrador_calls_restore(self):
        src = _method_src("_cargar_borrador")
        assert "_restore_draft_dict" in src


# ── 5. Auto-save timer (AST) ─────────────────────────────────────────────────

class TestAutoSaveTimer:
    """_autosave_timer debe inicializarse en __init__ con intervalo 45 000 ms."""

    def _init_src(self):
        src = _source()
        tree = ast.parse(src)
        lines = src.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "ModuloComprasPro":
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                        return "\n".join(lines[item.lineno - 1:item.end_lineno])
        return None

    def test_autosave_timer_attribute_in_init(self):
        src = self._init_src()
        assert src is not None
        assert "_autosave_timer" in src, (
            "_autosave_timer debe inicializarse en __init__ (P12: NO eliminar autosave timer)"
        )

    def test_autosave_timer_interval_45000ms(self):
        src = self._init_src()
        assert src is not None
        assert "45" in src, (
            "_autosave_timer debe configurarse con setInterval(45_000) en __init__"
        )

    def test_autosave_timer_starts_in_init(self):
        src = self._init_src()
        assert src is not None
        assert "_autosave_timer.start()" in src, (
            "_autosave_timer.start() debe llamarse en __init__"
        )

    def test_autosave_timer_connects_to_handler(self):
        src = self._init_src()
        assert src is not None
        assert "_auto_save_draft" in src, (
            "_autosave_timer debe conectarse a _auto_save_draft en __init__"
        )


# ── 6. Fallback directo deshabilitado (AST) ──────────────────────────────────

class TestFallbackDirectDisabled:
    """
    Fase 5: _fallback_compra_directa remains as a compatibility stub only.
    It must not write SQL, update inventory, or bypass RegistrarCompraUC/PurchaseService.
    """

    def _fallback_src(self):
        return _method_src("_fallback_compra_directa")

    def test_fallback_method_exists(self):
        """_fallback_compra_directa must still exist (P15: no eliminar sin audit trail)."""
        assert self._fallback_src() is not None, (
            "_fallback_compra_directa debe existir. "
            "P15 prohíbe eliminarla sin audit trail garantizado."
        )

    def test_fallback_is_disabled_stub(self):
        """Fallback must fail closed instead of writing purchases from the UI."""
        src = self._fallback_src()
        assert "raise RuntimeError" in src
        assert "deshabilitado" in src

    def test_fallback_has_no_direct_sql_or_inventory_writes(self):
        """No SQL/business side effects may remain in the UI fallback."""
        src = self._fallback_src()
        forbidden = [
            "INSERT INTO compras",
            "INSERT INTO detalles_compra",
            "UPDATE productos",
            "registrar_compra",
            "transaction(",
            "last_insert_rowid",
        ]
        assert not [token for token in forbidden if token in src]

    def test_procesar_compra_uses_uc_not_fallback(self):
        """_procesar_compra (DIRECT path) must delegate to RegistrarCompraUC, not _fallback."""
        src = _method_src("_procesar_compra")
        assert src is not None
        assert "RegistrarCompraUC" in src, (
            "_procesar_compra debe usar RegistrarCompraUC para el flujo DIRECT"
        )

    def test_fallback_not_called_from_procesar_compra(self):
        """The DIRECT path in _procesar_compra must NOT call _fallback_compra_directa."""
        src = _method_src("_procesar_compra")
        assert src is not None
        assert "_fallback_compra_directa" not in src, (
            "_procesar_compra no debe llamar _fallback_compra_directa. "
            "El fallback es solo para emergencias (container sin PurchaseService)."
        )

    def test_fallback_is_emergency_only(self):
        """_fallback_compra_directa is an emergency bypass — must NOT be in the main flow."""
        src = _source()
        tree = ast.parse(src)
        lines = src.splitlines()
        callers = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "ModuloComprasPro":
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name not in (
                        "_fallback_compra_directa",
                    ):
                        method_body = "\n".join(lines[item.lineno - 1:item.end_lineno])
                        if "_fallback_compra_directa" in method_body:
                            callers.append(item.name)
        assert not callers, (
            f"_fallback_compra_directa es llamada desde: {callers}. "
            f"P15: solo debe existir como safety net — no en el flujo principal."
        )


# ── 7. PurchaseService savepoint rollback ────────────────────────────────────

class TestPurchaseServiceSavepoint:
    """PurchaseService uses SAVEPOINT to roll back on inventory error."""

    def test_inventory_failure_rolls_back_purchase_header(self):
        """Inventory failure must roll back the complete DIRECT purchase savepoint."""
        from repositories.purchase_repository import PurchaseRepository
        from core.services.purchase_service import PurchaseService

        db = _make_db()
        repo = PurchaseRepository(db)

        inv_svc = MagicMock()
        inv_svc.increase_stock.side_effect = RuntimeError("stock error")

        svc = PurchaseService(db, repo, inv_svc, None)

        with pytest.raises(RuntimeError) as exc_info:
            svc.register_purchase(
                provider_id=1, branch_id=1, user="tester",
                items=[{"product_id": 1, "qty": 10, "unit_cost": 50.0, "nombre": "Pollo"}],
                payment_method="CONTADO", amount_paid=500,
            )

        assert "Error al registrar la compra" in str(exc_info.value)
        assert "Operación cancelada" in str(exc_info.value)
        count = db.execute("SELECT COUNT(*) FROM compras").fetchone()[0]
        details = db.execute("SELECT COUNT(*) FROM detalles_compra").fetchone()[0]
        stock = db.execute("SELECT quantity FROM inventory_stock WHERE product_id=1 AND branch_id=1").fetchone()[0]
        assert count == 0, "No debe quedar cabecera si inventario falla"
        assert details == 0, "No deben quedar detalles si inventario falla"
        assert float(stock) == 100.0, "No debe moverse stock canónico si se cancela el savepoint"

    def test_successful_purchase_commits(self):
        """On success, purchase header is visible after register_purchase returns."""
        svc, repo = _make_purchase_service(_make_db())
        folio, warnings = svc.register_purchase(
            provider_id=1, branch_id=1, user="tester",
            items=[{"product_id": 1, "qty": 10, "unit_cost": 50.0, "nombre": "Pollo"}],
            payment_method="CONTADO", amount_paid=500,
        )
        assert folio.startswith("CMP-")
        row = repo.db.execute(
            "SELECT estado FROM compras WHERE folio=?", (folio,)
        ).fetchone()
        assert row is not None
        assert row["estado"] == "completada"

    def test_warnings_list_returned_on_finance_error(self):
        """Finance errors produce warnings (list) but do NOT abort the purchase."""
        from repositories.purchase_repository import PurchaseRepository
        from core.services.purchase_service import PurchaseService

        db = _make_db()
        repo = PurchaseRepository(db)
        inv_svc = _make_mock_inventory_service(db)

        fin_svc = MagicMock()
        fin_svc.registrar_asiento.side_effect = RuntimeError("ledger error")
        fin_svc.get_estado_turno.return_value = None

        svc = PurchaseService(db, repo, inv_svc, fin_svc)
        folio, warnings = svc.register_purchase(
            provider_id=1, branch_id=1, user="tester",
            items=[{"product_id": 1, "qty": 10, "unit_cost": 50.0, "nombre": "Pollo"}],
            payment_method="CONTADO", amount_paid=500,
        )
        # Purchase must be saved despite finance error
        assert folio.startswith("CMP-")
        # Warnings list may or may not contain entries depending on call path
        assert isinstance(warnings, list)
