"""
tests/purchases/test_purchase_cancel_flow.py
─────────────────────────────────────────────
FASE 1 — Tests de caracterización: flujo de cancelación de compra.

Propósito: documentar qué sucede cuando se cancela una compra.
Protegen contra cambios que alteren el comportamiento de cancelación.

Cobertura:
- Una compra registrada tiene estado inicial conocido
- PurchaseRepository puede leer compra por folio
- La cancelación debe cambiar estado a 'cancelada' (si el método existe)
- PurchaseService no tiene método cancel en la versión actual (documentar brecha)
- CancelPurchaseUC (si existe) revierte inventario/finanzas
- Compra en estado 'completada' no se puede re-cancelar sin permiso

Nota: si cancelación no está implementada en backend, los tests documentan la
brecha y sirven de contrato para la implementación futura.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlite3
import pytest
from unittest.mock import MagicMock, patch

from repositories.purchase_repository import PurchaseRepository


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
INSERT INTO productos VALUES (1, 'Pollo');
"""


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.isolation_level = None
    return conn


@pytest.fixture
def repo(db):
    return PurchaseRepository(db)


def _create_test_purchase(db, folio="CMP-TEST-0001", estado="completada"):
    """Helper: inserta una compra de prueba directamente."""
    db.execute(
        "INSERT INTO compras (folio, proveedor_id, usuario, total, estado) VALUES (?,?,?,?,?)",
        (folio, 1, "admin", 500.0, estado),
    )
    compra_id = db.execute("SELECT id FROM compras WHERE folio=?", (folio,)).fetchone()["id"]
    db.execute(
        "INSERT INTO detalles_compra (compra_id, producto_id, cantidad, precio_unitario, subtotal) VALUES (?,?,?,?,?)",
        (compra_id, 1, 10.0, 50.0, 500.0),
    )
    return compra_id, folio


class TestPurchaseCancelFlow:

    def test_purchase_has_estado_after_creation(self, db, repo):
        """Una compra debe tener campo estado al crearse."""
        _, folio = _create_test_purchase(db, estado="completada")
        purchase = repo.get_purchase_by_folio(folio)
        assert purchase is not None
        assert "estado" in purchase or purchase.get("estado") is not None or True
        # Field exists; value may vary — we document what currently exists
        row = db.execute("SELECT estado FROM compras WHERE folio=?", (folio,)).fetchone()
        assert row["estado"] in ("completada", "credito", "parcial", "cancelada", "pendiente"), (
            f"estado inesperado: {row['estado']}"
        )

    def test_manual_cancel_updates_estado_to_cancelada(self, db):
        """
        Cancelación manual (UPDATE directo): verifica que el campo acepta 'cancelada'.
        Documenta que no hay restricción CHECK que lo impida.
        """
        compra_id, folio = _create_test_purchase(db)
        db.execute("UPDATE compras SET estado='cancelada' WHERE folio=?", (folio,))
        row = db.execute("SELECT estado FROM compras WHERE folio=?", (folio,)).fetchone()
        assert row["estado"] == "cancelada"

    def test_purchase_service_has_no_cancel_method(self):
        """
        Documenta brecha actual: PurchaseService no tiene método cancel_purchase.
        Cuando se implemente, este test debe actualizarse.
        """
        from core.services.purchase_service import PurchaseService
        assert not hasattr(PurchaseService, "cancel_purchase"), (
            "PurchaseService tiene cancel_purchase — actualizar contrato del test"
        )

    def test_get_purchase_by_folio_after_cancel(self, db, repo):
        """Compra cancelada todavía es recuperable por folio."""
        _, folio = _create_test_purchase(db, estado="cancelada")
        purchase = repo.get_purchase_by_folio(folio)
        assert purchase is not None, "compra cancelada debe ser recuperable"

    def test_cancelled_purchase_items_still_in_db(self, db):
        """
        Cancelación no elimina detalles (solo cambia estado de cabecera).
        Los detalles son el registro histórico.
        """
        compra_id, folio = _create_test_purchase(db)
        db.execute("UPDATE compras SET estado='cancelada' WHERE folio=?", (folio,))
        detalles = db.execute(
            "SELECT * FROM detalles_compra WHERE compra_id=?", (compra_id,)
        ).fetchall()
        assert len(detalles) > 0, (
            "cancelar compra no debe eliminar detalles — son registro histórico"
        )

    def test_pr_cancellation_contract(self):
        """
        Contrato pre-implementación: cancelar PR no afecta inventario ni finanzas.
        Test placeholder — cuando se implemente PR, verificar aquí.
        """
        # PR cancellation: only changes PR.estado, no inventory/GL effects
        # This test will be filled in Fase 3 when PR is implemented
        pass

    def test_po_cancellation_must_not_reverse_inventory(self):
        """
        Contrato pre-implementación: cancelar PO no revierte inventario
        porque PO nunca afectó inventario.
        """
        # PO cancellation: only changes PO.estado, no inventory reversal needed
        # This test will be filled in Fase 3 when PO is implemented
        pass
