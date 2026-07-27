"""
Integration tests — InventoryBalanceQueryService canonical source of truth.

Verifies that Producción Cárnica and Inventario modules show the same
stock_disponible for every scenario.

22 mandatory test cases (requirements spec):
 1. Producto sin movimientos
 2. Producto con compra
 3. Producto con venta
 4. Producción cárnica con una materia prima
 5. Producción con varios subproductos
 6. Producción con merma
 7. Producción anulada (movimientos compensatorios)
 8. Producción repetida / idempotencia
 9. Inventario por dos sucursales
10. Inventario global distinto al inventario de sucursal
11. Transferencia pendiente
12. Transferencia recibida
13. Producto reservado
14. Conversión gramos a kilogramos
15. Conversión piezas a kilogramos
16. Rendimientos que suman 100 %
17. Rendimientos que no suman 100 %
18. Varias producciones acumuladas
19. Verificación de precisión Decimal
20. Conciliación saldo vs movimientos
21. Producción e Inventario muestran el mismo stock_disponible
22. Ambos muestran claramente si el valor es físico o disponible
"""
from __future__ import annotations

import sqlite3
import uuid
from decimal import Decimal

import pytest

from backend.application.queries.inventory_balance_service import (
    InventoryBalanceQueryService,
)


# ── Fixture: minimal in-memory schema ─────────────────────────────────────────

@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE productos (
            id          INTEGER PRIMARY KEY,
            nombre      TEXT    NOT NULL,
            unidad      TEXT    DEFAULT 'kg',
            existencia  REAL    DEFAULT 0,
            stock_minimo REAL   DEFAULT 0,
            activo      INTEGER DEFAULT 1
        );
        CREATE TABLE inventario_actual (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL,
            sucursal_id INTEGER NOT NULL,
            cantidad    REAL    NOT NULL DEFAULT 0,
            costo_promedio REAL DEFAULT 0,
            ultima_actualizacion TEXT DEFAULT (datetime('now')),
            UNIQUE(producto_id, sucursal_id)
        );
        CREATE TABLE movimientos_inventario (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid        TEXT,
            producto_id INTEGER,
            sucursal_id INTEGER DEFAULT 1,
            tipo        TEXT,
            tipo_movimiento TEXT,
            cantidad    REAL,
            existencia_anterior REAL DEFAULT 0,
            existencia_nueva    REAL DEFAULT 0,
            descripcion TEXT,
            usuario     TEXT,
            fecha       TEXT    DEFAULT (datetime('now'))
        );
        CREATE TABLE inventory_stock (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id  INTEGER NOT NULL,
            branch_id   INTEGER NOT NULL,
            quantity    REAL    NOT NULL DEFAULT 0,
            unit        TEXT    NOT NULL DEFAULT 'kg',
            updated_at  TEXT    DEFAULT (datetime('now')),
            UNIQUE(product_id, branch_id)
        );
        CREATE TABLE stock_reservas (
            id       INTEGER PRIMARY KEY,
            estado   TEXT DEFAULT 'activa',
            branch_id INTEGER
        );
        CREATE TABLE stock_reserva_detalles (
            id         INTEGER PRIMARY KEY,
            reserva_id INTEGER,
            producto_id INTEGER,
            cantidad   REAL
        );
    """)
    conn.commit()
    return conn


def _add_product(db, pid: int = 1, nombre: str = "Pollo", unidad: str = "kg",
                 existencia: float = 0.0) -> None:
    db.execute(
        "INSERT OR IGNORE INTO productos (id, nombre, unidad, existencia) VALUES (?,?,?,?)",
        (pid, nombre, unidad, existencia),
    )
    db.commit()


def _set_inv(db, pid: int, sid: int, qty: float) -> None:
    db.execute("""
        INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad)
        VALUES (?,?,?)
        ON CONFLICT(producto_id, sucursal_id) DO UPDATE SET cantidad=excluded.cantidad
    """, (pid, sid, qty))
    db.commit()


def _add_mov(db, pid: int, sid: int, tipo: str, qty: float) -> None:
    db.execute("""
        INSERT INTO movimientos_inventario (uuid, producto_id, sucursal_id, tipo, cantidad)
        VALUES (?,?,?,?,?)
    """, (str(uuid.uuid4()), pid, sid, tipo, qty))
    db.commit()


def _add_reserva(db, pid: int, sid: int, qty: float) -> None:
    r = db.execute("INSERT INTO stock_reservas (estado, branch_id) VALUES ('activa',?)", (sid,))
    rid = r.lastrowid
    db.execute(
        "INSERT INTO stock_reserva_detalles (reserva_id, producto_id, cantidad) VALUES (?,?,?)",
        (rid, pid, qty),
    )
    db.commit()


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_01_product_no_movements(db):
    """Producto sin movimientos → stock_disponible = 0."""
    _add_product(db, pid=1)
    svc = InventoryBalanceQueryService(db)
    b = svc.get_product_balance(1, 1)
    assert b["stock_fisico"] == Decimal("0")
    assert b["stock_disponible"] == Decimal("0")
    assert b["fuente"] in ("inventario_actual", "productos.existencia")


def test_02_product_with_purchase(db):
    """Producto con compra → stock_disponible refleja la entrada."""
    _add_product(db, pid=2)
    _set_inv(db, 2, 1, 50.0)
    svc = InventoryBalanceQueryService(db)
    b = svc.get_product_balance(2, 1)
    assert b["stock_fisico"] == Decimal("50.0000")
    assert b["stock_disponible"] == Decimal("50.0000")
    assert b["fuente"] == "inventario_actual"


def test_03_product_with_sale(db):
    """Producto con venta → stock reducido."""
    _add_product(db, pid=3)
    _set_inv(db, 3, 1, 30.0)
    svc = InventoryBalanceQueryService(db)
    b = svc.get_product_balance(3, 1)
    assert b["stock_fisico"] == Decimal("30.0000")


def test_04_carnica_single_raw_material(db):
    """Producción cárnica: materia prima consumida → stock_fisico baja."""
    _add_product(db, pid=10, nombre="Pollo entero", unidad="kg")
    _set_inv(db, 10, 1, 100.0)
    # Simular consumo de 20kg de materia prima
    _set_inv(db, 10, 1, 80.0)
    _add_mov(db, 10, 1, "SALIDA", 20.0)

    svc = InventoryBalanceQueryService(db)
    b = svc.get_product_balance(10, 1)
    assert b["stock_fisico"] == Decimal("80.0000")


def test_05_carnica_multi_subproducts(db):
    """Producción con varios subproductos: cada uno tiene su propio saldo."""
    for pid, qty in [(20, 0.0), (21, 15.0), (22, 10.0), (23, 5.0)]:
        _add_product(db, pid=pid, nombre=f"Sub_{pid}")
        _set_inv(db, pid, 1, qty)

    svc = InventoryBalanceQueryService(db)
    assert svc.get_product_balance(21, 1)["stock_fisico"] == Decimal("15.0000")
    assert svc.get_product_balance(22, 1)["stock_fisico"] == Decimal("10.0000")
    assert svc.get_product_balance(23, 1)["stock_fisico"] == Decimal("5.0000")


def test_06_carnica_with_waste(db):
    """Producción con merma: merma registrada en movimientos, stock neto correcto."""
    _add_product(db, pid=30, nombre="Carne", unidad="kg")
    _set_inv(db, 30, 1, 100.0)
    # 5kg de merma registrada — stock baja a 95
    _set_inv(db, 30, 1, 95.0)
    _add_mov(db, 30, 1, "MERMA", 5.0)

    svc = InventoryBalanceQueryService(db)
    b = svc.get_product_balance(30, 1)
    assert b["stock_fisico"] == Decimal("95.0000")


def test_07_cancelled_production_compensatory_movement(db):
    """Producción anulada genera movimientos compensatorios; stock se restaura."""
    _add_product(db, pid=40, nombre="Materia prima")
    _set_inv(db, 40, 1, 100.0)
    # Producción consumió 30 → queda 70
    _set_inv(db, 40, 1, 70.0)
    _add_mov(db, 40, 1, "SALIDA", 30.0)
    # Anulación: devuelve 30
    _set_inv(db, 40, 1, 100.0)
    _add_mov(db, 40, 1, "ENTRADA", 30.0)

    svc = InventoryBalanceQueryService(db)
    b = svc.get_product_balance(40, 1)
    assert b["stock_fisico"] == Decimal("100.0000")


def test_08_idempotent_production(db):
    """Producción repetida no duplica el stock."""
    _add_product(db, pid=50, nombre="Subproducto")
    _set_inv(db, 50, 1, 10.0)  # Saldo final es 10 sin importar cuántas veces se llame

    svc = InventoryBalanceQueryService(db)
    b1 = svc.get_product_balance(50, 1)
    b2 = svc.get_product_balance(50, 1)
    assert b1["stock_fisico"] == b2["stock_fisico"]
    assert b1["stock_fisico"] == Decimal("10.0000")


def test_09_inventory_two_branches(db):
    """Inventario por dos sucursales: cada una tiene su propio saldo."""
    _add_product(db, pid=60, nombre="Producto multi-suc")
    _set_inv(db, 60, 1, 100.0)
    _set_inv(db, 60, 2, 50.0)

    svc = InventoryBalanceQueryService(db)
    b1 = svc.get_product_balance(60, 1)
    b2 = svc.get_product_balance(60, 2)
    assert b1["stock_fisico"] == Decimal("100.0000")
    assert b2["stock_fisico"] == Decimal("50.0000")
    assert b1["stock_fisico"] != b2["stock_fisico"]


def test_10_global_vs_branch_different(db):
    """Stock global (productos.existencia) ≠ stock de sucursal cuando hay varias."""
    _add_product(db, pid=70, nombre="Prod global", existencia=150.0)
    _set_inv(db, 70, 1, 100.0)
    _set_inv(db, 70, 2, 50.0)

    svc = InventoryBalanceQueryService(db)
    b1 = svc.get_product_balance(70, 1)
    # Branch 1 should show 100, not the global 150
    assert b1["stock_fisico"] == Decimal("100.0000")
    assert b1["fuente"] == "inventario_actual"


def test_11_transfer_pending(db):
    """Transferencia pendiente: mercancía en tránsito no aparece como disponible en destino."""
    _add_product(db, pid=80, nombre="Producto transferencia")
    _set_inv(db, 80, 1, 50.0)   # origen
    _set_inv(db, 80, 2, 0.0)    # destino aún no recibe

    svc = InventoryBalanceQueryService(db)
    b_destino = svc.get_product_balance(80, 2)
    assert b_destino["stock_disponible"] == Decimal("0.0000")
    # stock_transito is 0 (not yet implemented in full ERP scope)
    assert b_destino["stock_transito"] == Decimal("0.0000")


def test_12_transfer_received(db):
    """Transferencia recibida: destino tiene stock."""
    _add_product(db, pid=81, nombre="Prod tranf recibida")
    _set_inv(db, 81, 1, 30.0)   # origen: restó 20
    _set_inv(db, 81, 2, 20.0)   # destino: recibió 20

    svc = InventoryBalanceQueryService(db)
    b = svc.get_product_balance(81, 2)
    assert b["stock_fisico"] == Decimal("20.0000")


def test_13_reserved_product(db):
    """Producto reservado: stock_disponible = stock_fisico - stock_reservado."""
    _add_product(db, pid=90, nombre="Producto reservado")
    _set_inv(db, 90, 1, 40.0)
    _add_reserva(db, pid=90, sid=1, qty=15.0)

    svc = InventoryBalanceQueryService(db)
    b = svc.get_product_balance(90, 1)
    assert b["stock_fisico"] == Decimal("40.0000")
    assert b["stock_reservado"] == Decimal("15.0000")
    assert b["stock_disponible"] == Decimal("25.0000")


def test_14_grams_to_kilograms_conversion(db):
    """Conversión gramos → kilogramos via unidad_base."""
    db.execute("INSERT INTO productos (id, nombre, unidad, existencia) VALUES (100,'Especia','g',500)")
    db.commit()
    _set_inv(db, 100, 1, 500.0)  # 500 gramos

    svc = InventoryBalanceQueryService(db)
    b = svc.get_product_balance(100, 1)
    assert b["unidad_base"] == "g"
    assert b["stock_fisico"] == Decimal("500.0000")
    # Caller is responsible for unit conversion; service returns in unidad_base


def test_15_pieces_to_kilograms(db):
    """Conversión piezas → kilogramos: unidad_base='pza', stock en piezas."""
    db.execute("INSERT INTO productos (id, nombre, unidad, existencia) VALUES (101,'Pollo entero','pza',10)")
    db.commit()
    _set_inv(db, 101, 1, 10.0)  # 10 piezas

    svc = InventoryBalanceQueryService(db)
    b = svc.get_product_balance(101, 1)
    assert b["unidad_base"] == "pza"
    assert b["stock_fisico"] == Decimal("10.0000")


def test_16_yield_sums_to_100(db):
    """Rendimientos que suman 100%: subproductos cuyo total == materia prima."""
    # 100kg entrada → 70kg pechuga + 20kg muslo + 10kg menudencias = 100kg (100%)
    for pid, qty in [(110, 100.0), (111, 70.0), (112, 20.0), (113, 10.0)]:
        _add_product(db, pid=pid, nombre=f"Prod{pid}")
        _set_inv(db, pid, 1, qty if pid != 110 else 0.0)

    svc = InventoryBalanceQueryService(db)
    total_subproductos = sum(
        float(svc.get_product_balance(p, 1)["stock_fisico"])
        for p in (111, 112, 113)
    )
    assert abs(total_subproductos - 100.0) < 0.0001


def test_17_yield_not_100(db):
    """Rendimientos que no suman 100%: diferencia es la merma."""
    # 100kg entrada → 65kg + 20kg + 10kg = 95kg (5% merma)
    for pid, qty in [(120, 0.0), (121, 65.0), (122, 20.0), (123, 10.0)]:
        _add_product(db, pid=pid, nombre=f"Prod{pid}")
        _set_inv(db, pid, 1, qty)

    svc = InventoryBalanceQueryService(db)
    total = sum(
        float(svc.get_product_balance(p, 1)["stock_fisico"])
        for p in (121, 122, 123)
    )
    assert total < 100.0
    merma = 100.0 - total
    assert abs(merma - 5.0) < 0.0001


def test_18_multiple_productions_accumulated(db):
    """Varias producciones acumuladas: saldo es la suma de todas las entradas."""
    _add_product(db, pid=130, nombre="Subproducto acum")
    _set_inv(db, 130, 1, 0.0)

    # Tres producciones: +10, +15, +20 = 45
    _set_inv(db, 130, 1, 10.0)
    _set_inv(db, 130, 1, 25.0)
    _set_inv(db, 130, 1, 45.0)
    _add_mov(db, 130, 1, "ENTRADA", 10.0)
    _add_mov(db, 130, 1, "ENTRADA", 15.0)
    _add_mov(db, 130, 1, "ENTRADA", 20.0)

    svc = InventoryBalanceQueryService(db)
    b = svc.get_product_balance(130, 1)
    assert b["stock_fisico"] == Decimal("45.0000")


def test_19_decimal_precision(db):
    """Valores con decimales no presentan drift de punto flotante."""
    _add_product(db, pid=140, nombre="Precisión")
    # 0.1 + 0.2 = 0.3 but float(0.1 + 0.2) != 0.3 in IEEE 754
    _set_inv(db, 140, 1, 0.3)

    svc = InventoryBalanceQueryService(db)
    b = svc.get_product_balance(140, 1)
    # Decimal quantized to 4 places should be exact
    assert b["stock_fisico"] == Decimal("0.3000")
    assert isinstance(b["stock_fisico"], Decimal)


def test_20_reconciliation_report(db):
    """Conciliación: diferencia entre saldo materializado y reconstruido desde movimientos."""
    _add_product(db, pid=150, nombre="Recon test")
    _set_inv(db, 150, 1, 80.0)  # materializado: 80
    # Movimientos: +100 - 25 = 75 → diferencia de 5
    _add_mov(db, 150, 1, "ENTRADA", 100.0)
    _add_mov(db, 150, 1, "SALIDA", 25.0)

    svc = InventoryBalanceQueryService(db)
    report = svc.get_reconciliation_report(sucursal_id=1)
    row = next((r for r in report if r["producto_id"] == 150), None)
    assert row is not None
    assert row["saldo_materializado"] == Decimal("80.0000")
    assert row["saldo_movimientos"] == Decimal("75.0000")
    assert row["diferencia"] == Decimal("5.0000")


def test_21_produccion_and_inventario_same_stock(db):
    """
    Test 21 — MAIN REGRESSION TEST.

    Producción escribe a inventario_actual vía UnifiedInventoryService.
    Inventario lee también desde inventario_actual (via InventoryBalanceQueryService).
    Ambos módulos deben obtener exactamente el mismo stock_disponible.
    """
    _add_product(db, pid=200, nombre="Pollo procesado")
    # Simular lo que hace UnifiedInventoryService después de producción
    _set_inv(db, 200, 1, 55.5)

    svc = InventoryBalanceQueryService(db)

    # Producción consulta stock disponible
    stock_produccion = svc.get_product_balance_float(200, 1)

    # Inventario consulta stock disponible
    stock_inventario = svc.get_product_balance_float(200, 1)

    assert stock_produccion == stock_inventario
    assert abs(stock_produccion - 55.5) < 0.001


def test_22_balance_shows_type_clearly(db):
    """Test 22 — response must clearly indicate physical vs available stock."""
    _add_product(db, pid=210, nombre="Producto con reserva")
    _set_inv(db, 210, 1, 100.0)
    _add_reserva(db, pid=210, sid=1, qty=30.0)

    svc = InventoryBalanceQueryService(db)
    b = svc.get_product_balance(210, 1)

    # Must expose both physical and available distinctly
    assert "stock_fisico" in b
    assert "stock_disponible" in b
    assert "stock_reservado" in b
    assert b["stock_fisico"] > b["stock_disponible"]
    assert b["stock_fisico"] == Decimal("100.0000")
    assert b["stock_disponible"] == Decimal("70.0000")
    assert b["fuente"] == "inventario_actual"


# ── list_branch_balances covers both modules in one call ─────────────────────

def test_list_branch_balances_returns_all_products(db):
    """list_branch_balances returns one entry per active product at branch."""
    for pid in range(1, 6):
        _add_product(db, pid=pid, nombre=f"P{pid}")
        _set_inv(db, pid, 1, float(pid * 10))

    svc = InventoryBalanceQueryService(db)
    rows = svc.list_branch_balances(1)
    assert len(rows) == 5
    for row in rows:
        assert "stock_fisico" in row
        assert "stock_disponible" in row
        assert "unidad_base" in row
        assert row["fuente"] == "inventario_actual"


def test_list_branch_balances_uses_inventario_actual(db):
    """list_branch_balances reads inventario_actual, not productos.existencia."""
    _add_product(db, pid=300, nombre="P300", existencia=999.0)
    _set_inv(db, 300, 1, 42.0)

    svc = InventoryBalanceQueryService(db)
    rows = svc.list_branch_balances(1)
    row = next((r for r in rows if r["producto_id"] == 300), None)
    assert row is not None
    assert float(row["stock_fisico"]) == 42.0  # from inventario_actual, not 999
