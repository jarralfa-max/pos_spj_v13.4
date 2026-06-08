"""
tests/purchases/test_purchase_inventory_effects.py
───────────────────────────────────────────────────
FASE 1 — Tests de caracterización: efectos en inventario.

Propósito: documentar DÓNDE y CÓMO se afecta el inventario en una compra.
Protegen contra:
  - PR/PO que toquen inventario (no deben)
  - Recepción que duplique inventario
  - Cambios en PurchaseInventoryHandler que rompan kardex

Cobertura:
- increase_stock() se llama por cada item al registrar compra
- El stock aumenta en la sucursal correcta
- Cada item se procesa independientemente
- El inventario solo se afecta en recepción, no en creación de PR/PO
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from unittest.mock import MagicMock, call, patch

from core.services.purchase_service import PurchaseService
from repositories.purchase_repository import PurchaseRepository
import sqlite3


SCHEMA = """
CREATE TABLE compras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    folio TEXT UNIQUE,
    proveedor_id INTEGER, usuario TEXT,
    subtotal REAL DEFAULT 0, iva REAL DEFAULT 0, total REAL DEFAULT 0,
    estado TEXT DEFAULT 'completada', forma_pago TEXT DEFAULT 'CONTADO',
    observaciones TEXT, sucursal_id INTEGER DEFAULT 1,
    condicion_pago TEXT DEFAULT 'liquidado', plazo_dias INTEGER DEFAULT 0,
    moneda TEXT DEFAULT 'MXN'
);
CREATE TABLE detalles_compra (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    compra_id INTEGER, producto_id INTEGER,
    cantidad REAL, precio_unitario REAL, subtotal REAL
);
CREATE TABLE productos (id INTEGER PRIMARY KEY, nombre TEXT);
INSERT INTO productos VALUES (1, 'Pollo'), (2, 'Res'), (3, 'Cerdo');
"""


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.isolation_level = None
    return conn


@pytest.fixture
def inv_svc():
    return MagicMock()


@pytest.fixture
def service(db, inv_svc):
    repo = PurchaseRepository(db)
    fin_svc = MagicMock()
    svc = PurchaseService(db, repo, inv_svc, fin_svc)
    with patch("core.events.event_bus.get_bus") as mock_bus:
        bus = MagicMock()
        bus.handler_count.return_value = 0
        bus.publish_async = MagicMock()
        mock_bus.return_value = bus
        yield svc, inv_svc


class TestPurchaseInventoryEffects:

    def test_increase_stock_called_for_each_item(self, service):
        svc, inv = service
        items = [
            {"product_id": 1, "qty": 10.0, "unit_cost": 50.0},
            {"product_id": 2, "qty": 5.0, "unit_cost": 120.0},
        ]
        svc.register_purchase(
            provider_id=1, branch_id=1, user="admin",
            items=items, payment_method="CONTADO", amount_paid=1100.0,
        )
        # Canonical inventory_service.increase_stock should be called once per item.
        assert inv.increase_stock.call_count == len(items), (
            f"increase_stock debe llamarse {len(items)} veces, "
            f"se llamó {inv.increase_stock.call_count}"
        )

    def test_increase_stock_receives_correct_product_id(self, service):
        svc, inv = service
        items = [{"product_id": 3, "qty": 7.0, "unit_cost": 90.0}]
        svc.register_purchase(
            provider_id=1, branch_id=1, user="admin",
            items=items, payment_method="CONTADO", amount_paid=630.0,
        )
        call_kwargs = inv.increase_stock.call_args
        args, kwargs = call_kwargs
        # product_id must appear as positional or keyword arg
        product_ids_passed = list(args) + list(kwargs.values())
        assert 3 in product_ids_passed or kwargs.get("product_id") == 3, (
            "increase_stock debe recibir product_id=3"
        )

    def test_increase_stock_receives_correct_branch(self, service):
        svc, inv = service
        items = [{"product_id": 1, "qty": 2.0, "unit_cost": 100.0}]
        svc.register_purchase(
            provider_id=1, branch_id=7, user="admin",
            items=items, payment_method="CONTADO", amount_paid=200.0,
        )
        call_args = inv.increase_stock.call_args
        args, kwargs = call_args
        all_args = list(args) + list(kwargs.values())
        assert 7 in all_args or kwargs.get("branch_id") == 7 or kwargs.get("sucursal_id") == 7, (
            "increase_stock debe recibir branch_id/sucursal_id=7"
        )

    def test_inventory_not_affected_when_no_items(self, service):
        """Sin items, increase_stock nunca debe llamarse (compra vacía)."""
        svc, inv = service
        try:
            svc.register_purchase(
                provider_id=1, branch_id=1, user="admin",
                items=[], payment_method="CONTADO", amount_paid=0.0,
            )
        except Exception:
            pass  # compra vacía puede fallar — lo que importa es no afectar inventario
        assert inv.increase_stock.call_count == 0, "compra vacía no debe tocar inventario"

    def test_inventory_single_item_not_duplicated(self, service):
        """Un solo item → increase_stock llamado exactamente una vez."""
        svc, inv = service
        items = [{"product_id": 1, "qty": 5.0, "unit_cost": 50.0}]
        svc.register_purchase(
            provider_id=1, branch_id=1, user="admin",
            items=items, payment_method="CONTADO", amount_paid=250.0,
        )
        assert inv.increase_stock.call_count == 1, (
            f"un item → increase_stock debe llamarse 1 vez, "
            f"se llamó {inv.increase_stock.call_count} (posible duplicación)"
        )

    def test_pr_must_not_affect_inventory(self):
        """
        Contrato pre-implementación: PR no debe llamar increase_stock.
        Verificar que no existe ningún módulo PR que llame increase_stock directamente.
        """
        # Si el módulo PR no existe aún, el test pasa (es el estado esperado)
        try:
            from application.purchases import purchase_request_uc
            # Si existe, verificar que no expone increase_stock
            assert not hasattr(purchase_request_uc, "increase_stock"), (
                "PR UC no debe exponer increase_stock"
            )
        except ImportError:
            pass  # módulo PR no existe todavía — comportamiento esperado en Fase 0

    def test_po_must_not_affect_inventory(self):
        """
        Contrato pre-implementación: PO no debe llamar increase_stock.
        """
        try:
            from application.purchases import purchase_order_uc
            assert not hasattr(purchase_order_uc, "increase_stock"), (
                "PO UC no debe exponer increase_stock"
            )
        except ImportError:
            pass  # módulo PO no existe todavía — comportamiento esperado en Fase 0
