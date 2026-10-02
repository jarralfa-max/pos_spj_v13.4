"""Existencia real de un producto ANTES de una entrada, para el costeo.

El promedio móvil se calculaba con una "cantidad rastreada" que sólo sumaba
entradas y nunca restaba salidas: 100 kg @ $40, salen 90, entran 10 @ $60 →
(100×40 + 10×60) / 110 = $41.82 en vez de (10×40 + 10×60) / 20 = $50.

Inventario es el dueño de la existencia, así que la pregunta se le hace a él:
cuánto había del producto (en toda la empresa: el costo es global) antes de la
operación que está entrando. Como Inventario y Costeo escuchan el MISMO evento y
el orden de los manejadores no está garantizado, se toma la existencia actual y se
le resta lo que esa misma operación ya haya asentado — el resultado es igual
tanto si Inventario ya procesó la entrada como si todavía no.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal, InvalidOperation


def _dec(value) -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else "0"))
    except (InvalidOperation, ValueError):
        return Decimal("0")


class CostingStockQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def on_hand_before(self, product_id: str, *, operation_id: str,
                       branch_id: str | None = None) -> Decimal | None:
        """Existencia del producto previa a ``operation_id`` — de toda la empresa,
        o sólo de ``branch_id`` (costo por sucursal). ``None`` si el inventario
        canónico no existe en esta base (quien llama decide el respaldo). Nunca
        negativa: vender más de lo registrado no deja una existencia "negativa"
        que abarate el promedio."""
        balance_filter, ledger_filter, extra = "", "", ()
        if branch_id:
            balance_filter, ledger_filter, extra = " AND branch_id=?", " AND l.branch_id=?", (
                branch_id,)
        try:
            total = self._conn.execute(
                "SELECT COALESCE(SUM(CAST(quantity AS NUMERIC)), 0) FROM inventory_balances"
                " WHERE product_id=?" + balance_filter, (product_id, *extra)).fetchone()[0]
            posted_rows = self._conn.execute(
                "SELECT ll.quantity FROM inventory_ledger l"
                " JOIN inventory_ledger_lines ll ON ll.movement_id = l.id"
                # `operation_id` es ÚNICO en el libro: ese movimiento ES la entrada.
                " WHERE l.operation_id=? AND ll.product_id=?" + ledger_filter,
                (operation_id, product_id, *extra)).fetchall()
        except sqlite3.OperationalError:
            return None
        posted = sum((_dec(r[0]) for r in posted_rows), Decimal("0"))
        return max(Decimal("0"), _dec(total) - posted)
