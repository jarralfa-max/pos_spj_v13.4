"""Canonical warehouse lookup used to establish an explicit session context.

Estándar ÚNICO para "¿de qué almacén hace X esta sucursal?" (Fase 6 Ventas,
Fase 10 Cárnico). Cada almacén declara para qué sirve con sus casillas
(`allow_sales_allocation`, `allow_purchase_receipt`, `allow_production`); los
módulos no adivinan ni usan la sucursal como almacén cuando existe uno real.
"""

from __future__ import annotations

import sqlite3

#: Uso → columna que lo habilita en `warehouses`.
PURPOSE_COLUMN = {
    "SALES": "allow_sales_allocation",
    "PURCHASE": "allow_purchase_receipt",
    "PRODUCTION": "allow_production",
}

PURPOSE_LABEL = {"SALES": "venta", "PURCHASE": "compra", "PRODUCTION": "producción"}


class WarehouseDirectoryQueryService:
    def __init__(self, connection) -> None:
        self._connection = connection

    def active_for_branch(self, branch_id: str) -> list[tuple[str, str]]:
        try:
            rows = self._connection.execute(
                "SELECT id, code || ' · ' || name FROM warehouses"
                " WHERE branch_id=? AND status='ACTIVE' AND allow_purchase_receipt=1"
                " ORDER BY name", (branch_id,)).fetchall()
        except sqlite3.OperationalError:
            return []
        return [(str(row[0]), str(row[1])) for row in rows]

    def warehouses_for_purpose(self, branch_id: str, purpose: str) -> list[str]:
        """Almacenes ACTIVOS de la sucursal habilitados para `purpose`
        (SALES / PURCHASE / PRODUCTION)."""
        columna = PURPOSE_COLUMN[purpose]
        try:
            rows = self._connection.execute(
                f"SELECT id FROM warehouses WHERE branch_id=? AND status='ACTIVE'"
                f" AND {columna}=1 ORDER BY name", (branch_id,)).fetchall()
        except sqlite3.OperationalError:
            return []
        return [str(row[0]) for row in rows]

    def sales_warehouses_for_branch(self, branch_id: str) -> list[str]:
        """Almacenes ACTIVOS de la sucursal marcados para venta
        (`allow_sales_allocation`). Es de donde el mostrador descuenta."""
        return self.warehouses_for_purpose(branch_id, "SALES")

    def resolve_for_purpose(self, branch_id: str, purpose: str) -> tuple[str | None, str | None]:
        """(almacén, None) si hay exactamente uno habilitado para `purpose`;
        (None, motivo) si no hay ninguno o hay varios — nunca se adivina."""
        almacenes = self.warehouses_for_purpose(branch_id, purpose)
        uso = PURPOSE_LABEL.get(purpose, purpose.lower())
        if len(almacenes) == 1:
            return almacenes[0], None
        if not almacenes:
            return None, (f"La sucursal no tiene un almacén habilitado para {uso}. "
                          f"Márcalo en Inventario → Almacenes (casilla «{uso.capitalize()}»).")
        return None, (f"La sucursal tiene varios almacenes habilitados para {uso}; "
                      "deja sólo uno marcado en Inventario → Almacenes.")
