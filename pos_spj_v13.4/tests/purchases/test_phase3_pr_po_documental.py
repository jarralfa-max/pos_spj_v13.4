"""
tests/purchases/test_phase3_pr_po_documental.py
─────────────────────────────────────────────────
FASE 3 — Tests del modelo documental PR/PO.

Verifica:
1. Migraciones 076/077/078 corren sin error en DB en memoria
2. PurchaseRequestRepository: create, get, update_estado
3. PurchaseOrderRepository: create_from_pr, update_estado, completion
4. PurchaseRequestUC: ciclo completo de estados PR
5. PurchaseOrderUC: crear desde PR, enviar a recepción, cancelar
6. TraditionalPurchaseUC.execute() con document_type=PR
7. PR y PO NO afectan inventario ni GL
8. Transiciones inválidas de estado son rechazadas
9. Conversión PR → PO actualiza ambos estados correctamente
10. AppContainer registra uc_purchase_request y uc_purchase_order
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlite3
import importlib
import pytest
from unittest.mock import MagicMock


# ── Schema de prueba completo ─────────────────────────────────────────────────

BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS ordenes_compra (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid                   TEXT UNIQUE DEFAULT (lower(hex(randomblob(16)))),
    folio                  TEXT UNIQUE,
    proveedor_id           INTEGER,
    estado                 TEXT DEFAULT 'borrador',
    total                  REAL DEFAULT 0,
    notas                  TEXT,
    fecha_entrega_esperada DATE,
    fecha_recepcion        DATETIME,
    fecha_creacion         DATETIME DEFAULT (datetime('now')),
    usuario                TEXT
);
CREATE TABLE IF NOT EXISTS ordenes_compra_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    orden_id        INTEGER,
    producto_id     INTEGER,
    nombre          TEXT,
    cantidad        REAL,
    recibido        REAL DEFAULT 0,
    precio_unitario REAL,
    subtotal        REAL
);
CREATE TABLE IF NOT EXISTS compras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    folio TEXT UNIQUE, proveedor_id INTEGER, usuario TEXT,
    subtotal REAL DEFAULT 0, iva REAL DEFAULT 0, total REAL DEFAULT 0,
    estado TEXT DEFAULT 'completada', forma_pago TEXT DEFAULT 'CONTADO',
    observaciones TEXT, sucursal_id INTEGER DEFAULT 1,
    condicion_pago TEXT DEFAULT 'liquidado', plazo_dias INTEGER DEFAULT 0,
    moneda TEXT DEFAULT 'MXN'
);
CREATE TABLE IF NOT EXISTS productos (
    id INTEGER PRIMARY KEY, nombre TEXT, existencia REAL DEFAULT 100
);
INSERT INTO productos VALUES (1, 'Pollo Entero', 100), (2, 'Arrachera', 50);
"""


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(BASE_SCHEMA)
    conn.isolation_level = None
    # Run migrations 076, 077, 078
    for mod_name in [
        "migrations.standalone.076_purchase_requests",
        "migrations.standalone.077_ordenes_compra_erp",
        "migrations.standalone.078_compras_po_link",
    ]:
        mod = importlib.import_module(mod_name)
        mod.run(conn)
    return conn


@pytest.fixture
def pr_repo(db):
    from repositories.purchase_request_repository import PurchaseRequestRepository
    return PurchaseRequestRepository(db)


@pytest.fixture
def po_repo(db):
    from repositories.purchase_order_repository import PurchaseOrderRepository
    return PurchaseOrderRepository(db)


def _make_container(db, pr_repo, po_repo):
    container = MagicMock()
    container.purchase_request_repo = pr_repo
    container.purchase_order_repo   = po_repo
    return container


def _sample_items():
    return [
        {"product_id": 1, "qty": 10.0, "unit_cost": 50.0, "nombre": "Pollo"},
        {"product_id": 2, "qty": 5.0,  "unit_cost": 120.0, "nombre": "Arrachera"},
    ]


# ── Tests de migraciones ───────────────────────────────────────────────────────

class TestMigrations:

    def test_076_creates_purchase_requests_table(self, db):
        tables = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "purchase_requests" in tables
        assert "purchase_request_items" in tables

    def test_077_extends_ordenes_compra(self, db):
        cols = {r[1] for r in db.execute("PRAGMA table_info(ordenes_compra)")}
        for col in ("pr_id", "sucursal_id", "condicion_pago", "plazo_dias",
                    "moneda", "metodo_pago", "subtotal", "iva_monto"):
            assert col in cols, f"columna '{col}' falta en ordenes_compra tras migración 077"

    def test_077_extends_ordenes_compra_items(self, db):
        cols = {r[1] for r in db.execute("PRAGMA table_info(ordenes_compra_items)")}
        assert "unidad" in cols
        assert "lote" in cols

    def test_078_adds_purchase_order_id_to_compras(self, db):
        cols = {r[1] for r in db.execute("PRAGMA table_info(compras)")}
        assert "purchase_order_id" in cols

    def test_migrations_are_idempotent(self, db):
        """Correr migraciones dos veces no debe fallar."""
        for mod_name in [
            "migrations.standalone.076_purchase_requests",
            "migrations.standalone.077_ordenes_compra_erp",
            "migrations.standalone.078_compras_po_link",
        ]:
            mod = importlib.import_module(mod_name)
            mod.run(db)  # segunda vez — no debe lanzar excepción


# ── Tests de PurchaseRequestRepository ───────────────────────────────────────

class TestPurchaseRequestRepository:

    def test_create_returns_id_and_folio(self, pr_repo):
        pr_id, folio = pr_repo.create(
            proveedor_id=1, proveedor_nombre="Carnes Norte",
            sucursal_id=1, usuario="admin",
            items=_sample_items(),
            metodo_pago="CONTADO",
            subtotal=800.0, iva_monto=128.0, total=928.0,
        )
        assert pr_id > 0
        assert folio.startswith("PR-")

    def test_folio_format_starts_with_PR(self, pr_repo):
        _, folio = pr_repo.create(
            proveedor_id=1, proveedor_nombre="X",
            sucursal_id=1, usuario="admin",
            items=_sample_items(),
            metodo_pago="CONTADO",
            subtotal=100.0, iva_monto=0.0, total=100.0,
        )
        assert folio.startswith("PR-")

    def test_estado_inicial_borrador(self, db, pr_repo):
        pr_id, folio = pr_repo.create(
            proveedor_id=1, proveedor_nombre="X",
            sucursal_id=1, usuario="admin",
            items=_sample_items(),
            metodo_pago="CONTADO",
            subtotal=100.0, iva_monto=0.0, total=100.0,
        )
        row = db.execute("SELECT estado FROM purchase_requests WHERE id=?", (pr_id,)).fetchone()
        assert row["estado"] == "BORRADOR"

    def test_get_by_id_includes_items(self, pr_repo):
        pr_id, _ = pr_repo.create(
            proveedor_id=1, proveedor_nombre="X",
            sucursal_id=1, usuario="admin",
            items=_sample_items(),
            metodo_pago="CONTADO",
            subtotal=100.0, iva_monto=0.0, total=100.0,
        )
        pr = pr_repo.get_by_id(pr_id)
        assert pr is not None
        assert len(pr["items"]) == 2

    def test_update_estado_to_aprobada(self, db, pr_repo):
        pr_id, _ = pr_repo.create(
            proveedor_id=1, proveedor_nombre="X",
            sucursal_id=1, usuario="admin",
            items=_sample_items(),
            metodo_pago="CONTADO",
            subtotal=100.0, iva_monto=0.0, total=100.0,
        )
        pr_repo.update_estado(pr_id, "APROBADA", usuario="gerente")
        row = db.execute("SELECT estado, aprobado_por FROM purchase_requests WHERE id=?",
                         (pr_id,)).fetchone()
        assert row["estado"] == "APROBADA"
        assert row["aprobado_por"] == "gerente"

    def test_update_estado_to_rechazada_stores_motivo(self, db, pr_repo):
        pr_id, _ = pr_repo.create(
            proveedor_id=1, proveedor_nombre="X",
            sucursal_id=1, usuario="admin",
            items=_sample_items(),
            metodo_pago="CONTADO",
            subtotal=100.0, iva_monto=0.0, total=100.0,
        )
        pr_repo.update_estado(pr_id, "RECHAZADA", usuario="gerente",
                              motivo="Presupuesto insuficiente")
        row = db.execute(
            "SELECT motivo_rechazo FROM purchase_requests WHERE id=?", (pr_id,)
        ).fetchone()
        assert row["motivo_rechazo"] == "Presupuesto insuficiente"


# ── Tests de PurchaseOrderRepository ─────────────────────────────────────────

class TestPurchaseOrderRepository:

    def _make_pr_data(self):
        return {
            "proveedor_id": 1,
            "sucursal_id": 1,
            "subtotal": 800.0,
            "iva_monto": 128.0,
            "total": 928.0,
            "metodo_pago": "CONTADO",
            "condicion_pago": "liquidado",
            "plazo_dias": 0,
            "moneda": "MXN",
            "notas": "",
            "doc_ref": "FAC-001",
            "items": _sample_items(),
        }

    def test_create_from_pr_returns_id_and_folio(self, po_repo):
        po_id, folio = po_repo.create_from_pr(
            pr_id=1, pr_data=self._make_pr_data(), usuario="comprador"
        )
        assert po_id > 0
        assert folio.startswith("PO-")

    def test_po_estado_inicial_abierta(self, db, po_repo):
        po_id, _ = po_repo.create_from_pr(
            pr_id=1, pr_data=self._make_pr_data(), usuario="comprador"
        )
        row = db.execute("SELECT estado FROM ordenes_compra WHERE id=?", (po_id,)).fetchone()
        assert row["estado"] == "ABIERTA"

    def test_get_by_id_includes_items(self, po_repo):
        po_id, _ = po_repo.create_from_pr(
            pr_id=1, pr_data=self._make_pr_data(), usuario="comprador"
        )
        po = po_repo.get_by_id(po_id)
        assert po is not None
        assert len(po["items"]) == 2

    def test_compute_po_completion_zero_initially(self, po_repo):
        po_id, _ = po_repo.create_from_pr(
            pr_id=1, pr_data=self._make_pr_data(), usuario="comprador"
        )
        ratio = po_repo.compute_po_completion(po_id)
        assert ratio == 0.0

    def test_update_item_received_increments(self, po_repo):
        po_id, _ = po_repo.create_from_pr(
            pr_id=1, pr_data=self._make_pr_data(), usuario="comprador"
        )
        po_repo.update_item_received(po_id, producto_id=1, qty_received=5.0)
        ratio = po_repo.compute_po_completion(po_id)
        assert 0.0 < ratio < 1.0

    def test_full_receipt_gives_completion_1(self, po_repo):
        data = self._make_pr_data()
        data["items"] = [{"product_id": 1, "qty": 10.0, "unit_cost": 50.0, "nombre": "Pollo"}]
        po_id, _ = po_repo.create_from_pr(pr_id=1, pr_data=data, usuario="comprador")
        po_repo.update_item_received(po_id, producto_id=1, qty_received=10.0)
        ratio = po_repo.compute_po_completion(po_id)
        assert ratio >= 1.0


# ── Tests de PurchaseRequestUC ────────────────────────────────────────────────

class TestPurchaseRequestUC:

    def _make_command(self, **overrides):
        from application.purchases.commands import RegisterPurchaseCommand, PurchaseItemCommand
        from application.purchases.states import DocumentType
        defaults = dict(
            proveedor_id=1, proveedor_nombre="Carnes Norte",
            sucursal_id=1, usuario="admin",
            items=[PurchaseItemCommand(product_id=1, qty=10.0, unit_cost=50.0, nombre="Pollo")],
            metodo_pago="CONTADO",
            subtotal=500.0, iva_monto=80.0, total=580.0,
            document_type=DocumentType.PR,
        )
        defaults.update(overrides)
        return RegisterPurchaseCommand(**defaults)

    def test_crear_pr_returns_ok(self, db, pr_repo, po_repo):
        from application.purchases.purchase_request_uc import PurchaseRequestUC
        container = _make_container(db, pr_repo, po_repo)
        uc = PurchaseRequestUC(container)
        result = uc.crear_pr(self._make_command())
        assert result.ok, f"error: {result.error}"
        assert result.folio.startswith("PR-")
        assert result.estado == "BORRADOR"

    def test_enviar_aprobacion(self, db, pr_repo, po_repo):
        from application.purchases.purchase_request_uc import PurchaseRequestUC
        container = _make_container(db, pr_repo, po_repo)
        uc = PurchaseRequestUC(container)
        r = uc.crear_pr(self._make_command())
        r2 = uc.enviar_aprobacion(r.pr_id, "comprador")
        assert r2.ok
        assert r2.estado == "PENDIENTE_APROBACION"

    def test_aprobar_pr(self, db, pr_repo, po_repo):
        from application.purchases.purchase_request_uc import PurchaseRequestUC
        container = _make_container(db, pr_repo, po_repo)
        uc = PurchaseRequestUC(container)
        r = uc.crear_pr(self._make_command())
        uc.enviar_aprobacion(r.pr_id, "comprador")
        r3 = uc.aprobar(r.pr_id, "gerente")
        assert r3.ok
        assert r3.estado == "APROBADA"

    def test_rechazar_pr(self, db, pr_repo, po_repo):
        from application.purchases.purchase_request_uc import PurchaseRequestUC
        container = _make_container(db, pr_repo, po_repo)
        uc = PurchaseRequestUC(container)
        r = uc.crear_pr(self._make_command())
        uc.enviar_aprobacion(r.pr_id, "comprador")
        r3 = uc.rechazar(r.pr_id, "gerente", "Sin presupuesto")
        assert r3.ok
        assert r3.estado == "RECHAZADA"

    def test_invalid_transition_returns_error(self, db, pr_repo, po_repo):
        from application.purchases.purchase_request_uc import PurchaseRequestUC
        container = _make_container(db, pr_repo, po_repo)
        uc = PurchaseRequestUC(container)
        r = uc.crear_pr(self._make_command())
        # BORRADOR → APROBADA directamente: inválido
        r2 = uc.aprobar(r.pr_id, "gerente")
        assert not r2.ok
        assert "inválida" in r2.error.lower() or "Transición" in r2.error

    def test_convertir_a_po_creates_po(self, db, pr_repo, po_repo):
        from application.purchases.purchase_request_uc import PurchaseRequestUC
        container = _make_container(db, pr_repo, po_repo)
        uc = PurchaseRequestUC(container)
        r = uc.crear_pr(self._make_command())
        uc.enviar_aprobacion(r.pr_id, "comprador")
        uc.aprobar(r.pr_id, "gerente")
        r_po = uc.convertir_a_po(r.pr_id, "comprador")
        assert r_po.ok, f"error: {r_po.error}"
        assert r_po.po_id > 0
        assert r_po.po_folio.startswith("PO-")
        assert r_po.estado == "CONVERTIDA_A_PO"

    def test_convertir_a_po_marks_pr_estado(self, db, pr_repo, po_repo):
        from application.purchases.purchase_request_uc import PurchaseRequestUC
        container = _make_container(db, pr_repo, po_repo)
        uc = PurchaseRequestUC(container)
        r = uc.crear_pr(self._make_command())
        uc.enviar_aprobacion(r.pr_id, "comprador")
        uc.aprobar(r.pr_id, "gerente")
        uc.convertir_a_po(r.pr_id, "comprador")
        pr = pr_repo.get_by_id(r.pr_id)
        assert pr["estado"] == "CONVERTIDA_A_PO"

    def test_pr_does_not_call_add_stock(self, db, pr_repo, po_repo):
        from application.purchases.purchase_request_uc import PurchaseRequestUC
        inv_svc = MagicMock()
        container = _make_container(db, pr_repo, po_repo)
        container.inventory_service = inv_svc
        uc = PurchaseRequestUC(container)
        r = uc.crear_pr(self._make_command())
        assert r.ok
        inv_svc.add_stock.assert_not_called()

    def test_pr_does_not_call_registrar_asiento(self, db, pr_repo, po_repo):
        from application.purchases.purchase_request_uc import PurchaseRequestUC
        fin_svc = MagicMock()
        container = _make_container(db, pr_repo, po_repo)
        container.finance_service = fin_svc
        uc = PurchaseRequestUC(container)
        r = uc.crear_pr(self._make_command())
        assert r.ok
        fin_svc.registrar_asiento.assert_not_called()


# ── Tests de PurchaseOrderUC ──────────────────────────────────────────────────

class TestPurchaseOrderUC:

    def _setup_approved_pr(self, db, pr_repo, po_repo):
        from application.purchases.purchase_request_uc import PurchaseRequestUC
        from application.purchases.commands import RegisterPurchaseCommand, PurchaseItemCommand
        from application.purchases.states import DocumentType
        container = _make_container(db, pr_repo, po_repo)
        uc = PurchaseRequestUC(container)
        cmd = RegisterPurchaseCommand(
            proveedor_id=1, proveedor_nombre="Carnes Norte",
            sucursal_id=1, usuario="admin",
            items=[PurchaseItemCommand(product_id=1, qty=10.0, unit_cost=50.0, nombre="Pollo")],
            metodo_pago="CONTADO",
            subtotal=500.0, iva_monto=0.0, total=500.0,
            document_type=DocumentType.PR,
        )
        r = uc.crear_pr(cmd)
        uc.enviar_aprobacion(r.pr_id, "comprador")
        uc.aprobar(r.pr_id, "gerente")
        pr_data = pr_repo.get_by_id(r.pr_id)
        return r.pr_id, pr_data, container

    def test_crear_desde_pr_ok(self, db, pr_repo, po_repo):
        from application.purchases.purchase_order_uc import PurchaseOrderUC
        pr_id, pr_data, container = self._setup_approved_pr(db, pr_repo, po_repo)
        po_uc = PurchaseOrderUC(container)
        result = po_uc.crear_desde_pr(pr_id, pr_data, "comprador")
        assert result.ok, f"error: {result.error}"
        assert result.po_folio.startswith("PO-")
        assert result.estado == "ABIERTA"

    def test_enviar_a_recepcion_ok(self, db, pr_repo, po_repo):
        from application.purchases.purchase_order_uc import PurchaseOrderUC
        pr_id, pr_data, container = self._setup_approved_pr(db, pr_repo, po_repo)
        po_uc = PurchaseOrderUC(container)
        r = po_uc.crear_desde_pr(pr_id, pr_data, "comprador")
        r2 = po_uc.enviar_a_recepcion(r.po_id, "comprador")
        assert r2.ok
        assert r2.estado == "PARA_RECEPCION"

    def test_cancelar_po_abierta(self, db, pr_repo, po_repo):
        from application.purchases.purchase_order_uc import PurchaseOrderUC
        pr_id, pr_data, container = self._setup_approved_pr(db, pr_repo, po_repo)
        po_uc = PurchaseOrderUC(container)
        r = po_uc.crear_desde_pr(pr_id, pr_data, "comprador")
        r2 = po_uc.cancelar(r.po_id, "admin")
        assert r2.ok
        assert r2.estado == "CANCELADA"

    def test_po_does_not_call_add_stock(self, db, pr_repo, po_repo):
        from application.purchases.purchase_order_uc import PurchaseOrderUC
        inv_svc = MagicMock()
        pr_id, pr_data, container = self._setup_approved_pr(db, pr_repo, po_repo)
        container.inventory_service = inv_svc
        po_uc = PurchaseOrderUC(container)
        po_uc.crear_desde_pr(pr_id, pr_data, "comprador")
        inv_svc.add_stock.assert_not_called()

    def test_po_does_not_call_registrar_asiento(self, db, pr_repo, po_repo):
        from application.purchases.purchase_order_uc import PurchaseOrderUC
        fin_svc = MagicMock()
        pr_id, pr_data, container = self._setup_approved_pr(db, pr_repo, po_repo)
        container.finance_service = fin_svc
        po_uc = PurchaseOrderUC(container)
        po_uc.crear_desde_pr(pr_id, pr_data, "comprador")
        fin_svc.registrar_asiento.assert_not_called()

    def test_get_lineas_esperadas(self, db, pr_repo, po_repo):
        from application.purchases.purchase_order_uc import PurchaseOrderUC
        pr_id, pr_data, container = self._setup_approved_pr(db, pr_repo, po_repo)
        po_uc = PurchaseOrderUC(container)
        r = po_uc.crear_desde_pr(pr_id, pr_data, "comprador")
        lines = po_uc.get_lineas_esperadas(r.po_id)
        assert len(lines) == 1
        assert lines[0]["producto_id"] == 1


# ── Tests de TraditionalPurchaseUC con PR ─────────────────────────────────────

class TestTraditionalPurchaseUCWithPR:

    def _make_pr_command(self):
        from application.purchases.commands import RegisterPurchaseCommand, PurchaseItemCommand
        from application.purchases.states import DocumentType
        return RegisterPurchaseCommand(
            proveedor_id=1, proveedor_nombre="Proveedor",
            sucursal_id=1, usuario="admin",
            items=[PurchaseItemCommand(product_id=1, qty=5.0, unit_cost=100.0, nombre="Pollo")],
            metodo_pago="CONTADO",
            subtotal=500.0, iva_monto=0.0, total=500.0,
            document_type=DocumentType.PR,
        )

    def test_execute_pr_returns_purchase_result_ok(self, db, pr_repo, po_repo):
        from application.purchases.traditional_purchase_uc import TraditionalPurchaseUC
        from application.purchases.results import PurchaseResult
        from application.purchases.states import DocumentType
        container = _make_container(db, pr_repo, po_repo)
        uc = TraditionalPurchaseUC(container)
        result = uc.execute(self._make_pr_command())
        assert isinstance(result, PurchaseResult)
        assert result.ok, f"error: {result.error}"
        assert result.folio.startswith("PR-")
        assert result.document_type == DocumentType.PR

    def test_execute_pr_does_not_call_purchase_service(self, db, pr_repo, po_repo):
        from application.purchases.traditional_purchase_uc import TraditionalPurchaseUC
        container = _make_container(db, pr_repo, po_repo)
        container.purchase_service = MagicMock()
        uc = TraditionalPurchaseUC(container)
        uc.execute(self._make_pr_command())
        container.purchase_service.register_purchase.assert_not_called()


# ── Tests de AppContainer wiring Phase 3 ──────────────────────────────────────

class TestAppContainerPhase3:

    def test_app_container_has_uc_purchase_request(self):
        import inspect
        from core.app_container import AppContainer
        source = inspect.getsource(AppContainer.__init__)
        assert "uc_purchase_request" in source

    def test_app_container_has_uc_purchase_order(self):
        import inspect
        from core.app_container import AppContainer
        source = inspect.getsource(AppContainer.__init__)
        assert "uc_purchase_order" in source

    def test_app_container_has_purchase_request_repo(self):
        import inspect
        from core.app_container import AppContainer
        source = inspect.getsource(AppContainer.__init__)
        assert "purchase_request_repo" in source

    def test_app_container_has_purchase_order_repo(self):
        import inspect
        from core.app_container import AppContainer
        source = inspect.getsource(AppContainer.__init__)
        assert "purchase_order_repo" in source

    def test_migrations_registered_in_engine(self):
        from migrations.engine import MIGRATIONS
        versions = {v for v, _ in MIGRATIONS}
        assert "076" in versions
        assert "077" in versions
        assert "078" in versions
