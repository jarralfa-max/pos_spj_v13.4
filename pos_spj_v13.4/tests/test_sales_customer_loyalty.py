# tests/test_sales_customer_loyalty.py — SPJ POS v13.4
"""
Tests de integración: Customer & Loyalty en el flujo de checkout.

Cubre los 6 escenarios mandatorios:
1. Venta con cliente + pago en efectivo
2. Venta con cliente + crédito válido
3. Venta con cliente + crédito insuficiente → error
4. Venta con canje de puntos de lealtad
5. Venta acumula puntos de lealtad post-pago
6. Venta sin cliente (público general) — debe funcionar
"""
import sys
import os
import sqlite3
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db_checkout():
    """BD en memoria con schema completo para checkout (crédito + lealtad)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY, nombre TEXT NOT NULL,
            precio REAL DEFAULT 0, precio_compra REAL DEFAULT 0,
            existencia REAL DEFAULT 100, stock_minimo REAL DEFAULT 5,
            unidad TEXT DEFAULT 'pza', categoria TEXT, activo INTEGER DEFAULT 1
        );
        CREATE TABLE movimientos_inventario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT, producto_id INTEGER, sucursal_id INTEGER DEFAULT 1,
            tipo_movimiento TEXT, referencia_tipo TEXT, referencia_id TEXT,
            cantidad REAL, costo_unitario REAL DEFAULT 0,
            operation_id TEXT, usuario TEXT, nota TEXT,
            existencia_anterior REAL, existencia_nueva REAL,
            fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT, folio TEXT, sucursal_id INTEGER DEFAULT 1,
            usuario TEXT, cliente_id INTEGER,
            subtotal REAL, descuento REAL DEFAULT 0, total REAL,
            forma_pago TEXT DEFAULT 'Efectivo',
            efectivo_recibido REAL DEFAULT 0, cambio REAL DEFAULT 0,
            estado TEXT DEFAULT 'completada',
            operation_id TEXT, observations TEXT,
            fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE detalles_venta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id INTEGER, producto_id INTEGER,
            cantidad REAL, precio_unitario REAL,
            descuento REAL DEFAULT 0, subtotal REAL,
            unidad TEXT DEFAULT 'pza', comentarios TEXT
        );
        CREATE TABLE movimientos_caja (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT, monto REAL, descripcion TEXT,
            usuario TEXT, venta_id INTEGER, forma_pago TEXT,
            fecha DATETIME DEFAULT (datetime('now'))
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
            batch_id INTEGER,
            updated_at DATETIME DEFAULT (datetime('now')),
            UNIQUE(product_id, branch_id, batch_id)
        );
        CREATE TABLE clientes (
            id INTEGER PRIMARY KEY, nombre TEXT,
            credit_limit REAL DEFAULT 0, credit_balance REAL DEFAULT 0,
            puntos INTEGER DEFAULT 0, activo INTEGER DEFAULT 1
        );
        CREATE TABLE historico_puntos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER, tipo TEXT, puntos INTEGER,
            descripcion TEXT, venta_id INTEGER, fecha DATETIME
        );
        CREATE TABLE sync_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tabla TEXT, operacion TEXT, registro_id INTEGER,
            payload TEXT, sucursal_id INTEGER DEFAULT 1,
            estado TEXT DEFAULT 'pendiente',
            fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE recetas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER, componente_id INTEGER,
            cantidad REAL DEFAULT 1.0
        );

        INSERT INTO productos(id, nombre, precio, existencia, stock_minimo) VALUES
            (1, 'Pollo Entero', 150.0, 50.0, 5.0),
            (2, 'Agua 1L',       20.0, 200.0, 20.0);

        INSERT INTO inventario_actual(producto_id, sucursal_id, cantidad) VALUES
            (1, 1, 50.0),
            (2, 1, 200.0);

        INSERT INTO clientes(id, nombre, credit_limit, credit_balance, puntos, activo) VALUES
            (1, 'Juan Perez',  500.0,  0.0, 100, 1),
            (2, 'Maria Lopez',  50.0, 45.0,   0, 1);
    """)
    conn.commit()
    return conn


class MockLoyaltyService:
    """
    Stub de LoyaltyService para tests sin PyQt5 / GrowthEngine.
    Implementa exactamente la interfaz usada por SalesService y CustomerCreditService.
    """

    def __init__(self):
        self._ledger = []
        self._saldos = {1: 100, 2: 0}

    def compute_redemption_discount(self, pts: int, subtotal: float) -> float:
        valor_por_estrella = 0.10
        return round(min(pts * valor_por_estrella, subtotal * 0.5), 2)

    def process_loyalty_for_sale(self, client_id, total_sale, branch_id=1):
        earned = int(total_sale // 10)
        self._saldos[client_id] = self._saldos.get(client_id, 0) + earned
        return {
            "puntos_ganados": earned,
            "puntos_totales": self._saldos[client_id],
            "nivel": "Bronce",
            "mensaje": "¡Puntos acumulados!",
        }

    def registrar_en_ledger(self, cliente_id, tipo, puntos, referencia="",
                             descripcion="", usuario="", monto_equiv=0.0):
        self._ledger.append({
            "cliente_id": cliente_id,
            "tipo": tipo,
            "puntos": puntos,
            "referencia": referencia,
        })
        return True

    def get_ledger(self):
        return list(self._ledger)


@pytest.fixture
def sales_svc_checkout(db_checkout):
    """SalesService completo para tests de checkout (cliente + crédito + lealtad)."""
    from core.services.sales_service import SalesService
    from core.services.inventory_service import InventoryService
    from repositories.inventory_repository import InventoryRepository
    from repositories.sales_repository import SalesRepository
    from repositories.recetas import RecetaRepository as RecipeRepository
    from application.services.customer_credit_service import CustomerCreditService

    inv_repo    = InventoryRepository(db_checkout)
    sales_repo  = SalesRepository(db_checkout)
    recipe_repo = RecipeRepository(db_checkout)

    class _FakeAudit:
        def log_change(self, **kw): pass

    class _FakeFinance:
        def register_income(self, **kw): pass
        def registrar_asiento(self, **kw): pass
        def validar_margen(self, *a, **kw): return True

    class _FakeFlags:
        def is_enabled(self, *a, **kw): return True

    class _FakeConfig:
        def get(self, *a, **kw): return None

    class _FakeTicket:
        def generar_ticket(self, *a, **kw): return ""

    inv_svc         = InventoryService(db_checkout, inv_repo)
    loyalty_svc     = MockLoyaltyService()
    customer_svc    = CustomerCreditService(db_checkout, finance_service=_FakeFinance())

    return SalesService(
        db_conn                = db_checkout,
        sales_repo             = sales_repo,
        recipe_repo            = recipe_repo,
        inventory_service      = inv_svc,
        finance_service        = _FakeFinance(),
        loyalty_service        = loyalty_svc,
        promotion_engine       = None,
        sync_service           = None,
        ticket_template_engine = _FakeTicket(),
        whatsapp_service       = None,
        config_service         = _FakeConfig(),
        feature_flag_service   = _FakeFlags(),
        customer_service       = customer_svc,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _item(product_id=1, qty=1.0, unit_price=150.0, name="Pollo"):
    return {"product_id": product_id, "qty": qty, "unit_price": unit_price,
            "name": name, "es_compuesto": 0}


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestSaleWithCustomer:

    def test_sale_with_customer_cash_payment(self, sales_svc_checkout, db_checkout):
        """Venta con cliente identificado + efectivo: registra venta y asocia cliente."""
        folio, _ = sales_svc_checkout.execute_sale(
            branch_id=1, user="cajero",
            items=[_item()],
            payment_method="Efectivo",
            amount_paid=200.0,
            client_id=1,
        )
        assert folio.startswith("V")
        row = db_checkout.execute(
            "SELECT cliente_id, total FROM ventas WHERE folio=?", (folio,)
        ).fetchone()
        assert row is not None
        assert row["cliente_id"] == 1
        assert float(row["total"]) == pytest.approx(150.0)

    def test_sale_with_credit_valid(self, sales_svc_checkout, db_checkout):
        """Venta a crédito con límite suficiente: crea registro en cuentas_por_cobrar."""
        folio, _ = sales_svc_checkout.execute_sale(
            branch_id=1, user="cajero",
            items=[_item()],           # $150
            payment_method="Credito",
            amount_paid=0.0,
            client_id=1,               # limit=$500, balance=$0
        )
        cxc = db_checkout.execute(
            "SELECT saldo_pendiente, estado FROM cuentas_por_cobrar WHERE folio=?",
            (folio,)
        ).fetchone()
        assert cxc is not None
        assert float(cxc["saldo_pendiente"]) == pytest.approx(150.0)
        assert cxc["estado"] == "pendiente"

        # credit_balance del cliente debe haberse actualizado
        bal = db_checkout.execute(
            "SELECT credit_balance FROM clientes WHERE id=1"
        ).fetchone()
        assert float(bal["credit_balance"]) == pytest.approx(150.0)

    def test_sale_with_credit_insufficient_raises(self, sales_svc_checkout):
        """Venta a crédito con límite insuficiente: debe lanzar ValueError."""
        with pytest.raises((ValueError, RuntimeError)):
            sales_svc_checkout.execute_sale(
                branch_id=1, user="cajero",
                items=[_item(qty=1.0, unit_price=20.0)],  # $20 > disponible $5
                payment_method="Credito",
                amount_paid=0.0,
                client_id=2,               # limit=$50, balance=$45 → disponible=$5
            )

    def test_sale_with_invalid_customer_raises(self, sales_svc_checkout):
        """Cliente inexistente debe lanzar error antes de ejecutar la venta."""
        with pytest.raises((ValueError, RuntimeError)):
            sales_svc_checkout.execute_sale(
                branch_id=1, user="cajero",
                items=[_item()],
                payment_method="Efectivo",
                amount_paid=200.0,
                client_id=9999,
            )


class TestLoyaltyIntegration:

    def test_sale_with_loyalty_redemption(self, sales_svc_checkout, db_checkout):
        """Canje de 50 puntos ($5) descuenta el total antes del pago."""
        # $150 - $5 (50 pts × $0.10) = $145
        folio, _ = sales_svc_checkout.execute_sale(
            branch_id=1, user="cajero",
            items=[_item()],           # $150
            payment_method="Efectivo",
            amount_paid=145.0,
            client_id=1,
            loyalty_redemption_pts=50,
        )
        row = db_checkout.execute(
            "SELECT total, descuento FROM ventas WHERE folio=?", (folio,)
        ).fetchone()
        assert float(row["total"]) == pytest.approx(145.0)
        assert float(row["descuento"]) == pytest.approx(5.0)

    def test_sale_loyalty_redemption_logged_in_ledger(self, sales_svc_checkout):
        """El canje debe quedar registrado en el ledger de lealtad."""
        sales_svc_checkout.execute_sale(
            branch_id=1, user="cajero",
            items=[_item()],
            payment_method="Efectivo",
            amount_paid=145.0,
            client_id=1,
            loyalty_redemption_pts=50,
        )
        ledger = sales_svc_checkout.loyalty_service.get_ledger()
        canje_entries = [e for e in ledger if e["tipo"] == "canje"]
        assert len(canje_entries) >= 1
        assert canje_entries[0]["puntos"] == -50

    def test_sale_accumulates_loyalty_points(self, sales_svc_checkout):
        """Después de la venta, process_loyalty_for_sale acredita puntos al cliente."""
        initial_saldo = sales_svc_checkout.loyalty_service._saldos.get(1, 0)
        sales_svc_checkout.execute_sale(
            branch_id=1, user="cajero",
            items=[_item()],           # $150 → 15 pts a $1/10
            payment_method="Efectivo",
            amount_paid=200.0,
            client_id=1,
        )
        new_saldo = sales_svc_checkout.loyalty_service._saldos.get(1, 0)
        assert new_saldo > initial_saldo

    def test_sale_without_customer_still_works(self, sales_svc_checkout, db_checkout):
        """Venta sin cliente (público general) no debe fallar."""
        folio, _ = sales_svc_checkout.execute_sale(
            branch_id=1, user="cajero",
            items=[_item()],
            payment_method="Efectivo",
            amount_paid=200.0,
            client_id=None,
        )
        assert folio.startswith("V")
        row = db_checkout.execute(
            "SELECT total FROM ventas WHERE folio=?", (folio,)
        ).fetchone()
        assert float(row["total"]) == pytest.approx(150.0)
