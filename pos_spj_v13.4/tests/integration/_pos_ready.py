"""Lo que un mostrador necesita para cobrar desde la Fase 6 (2026-09-18).

El cobro exige un turno de caja abierto del cajero y descuenta inventario de
verdad. Las pruebas que pasan por la composición real del POS lo siembran con
estas dos ayudas en vez de apagar las reglas: así prueban lo mismo que corre en
producción.
"""
from __future__ import annotations

import importlib
from decimal import Decimal

from backend.shared.ids import new_uuid


def open_cash_shift(conn, *, branch_id: str, cashier_user_id: str) -> str:
    """Esquema real de Caja (migración 175) + caja, cajón, terminal y un turno
    ABIERTO del cajero en la sucursal. Devuelve el id del turno."""
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='cash_shifts'").fetchone() is None:
        # Sólo el DDL de la 175: su `run()` termina con un `foreign_key_check`
        # de TODA la base, que en una prueba ya sembrada (recetas, productos)
        # falla por datos ajenos a Caja.
        m175 = importlib.import_module(
            "migrations.standalone.175_cash_register_bounded_context_schema")
        for statement in (*m175.DDL, *m175.INDEXES):
            conn.execute(statement)
    register, drawer, terminal, shift = new_uuid(), new_uuid(), new_uuid(), new_uuid()
    now = "2026-09-18T12:00:00+00:00"
    conn.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                 (register, branch_id, "Caja 1", "ACTIVE", None, now, now))
    conn.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                 (drawer, branch_id, register, "Cajón 1", "ACTIVE", now, now))
    conn.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                 (terminal, branch_id, register, "Terminal 1", "ACTIVE", now, now))
    conn.execute(
        "INSERT INTO cash_shifts (id, branch_id, register_id, drawer_id, terminal_id, "
        "cashier_user_id, opening_amount, opening_operation_id, status, opened_at) "
        "VALUES (?,?,?,?,?,?,?,?, 'OPEN', ?)",
        (shift, branch_id, register, drawer, terminal, cashier_user_id, "0", new_uuid(), now))
    conn.commit()
    return shift


def stock_product(conn, *, product_id: str, branch_id: str, quantity,
                  warehouse_id: str | None = None) -> None:
    """Existencia disponible del producto (sin almacén propio, la sucursal hace
    de almacén: la convención que conserva `SalesInventoryClient`)."""
    from backend.domain.inventory.entities.inventory_balance import InventoryBalance
    from backend.domain.inventory.enums import InventoryStatus
    from backend.infrastructure.db.repositories.inventory.unit_of_work import (
        InventoryUnitOfWork,
    )
    if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='inventory_balances'").fetchone() is None:
        from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
        create_inventory_schema(conn)
    bal = InventoryBalance.empty(
        product_id=product_id, branch_id=branch_id, warehouse_id=warehouse_id or branch_id,
        inventory_status=InventoryStatus.AVAILABLE, location_id=branch_id)
    bal.apply_delta(quantity=Decimal(str(quantity)))
    with InventoryUnitOfWork(conn) as uow:
        uow.balances.upsert(bal)
