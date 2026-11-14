"""Tesorería ← Caja: el depósito que Caja preparó y su confirmación (SDLC-CASH-002).

Único punto donde Finanzas toca esas tablas: lee `cash_deposit_preparations`,
que es de Caja, y escribe `cash_deposit_confirmations`, que es de Tesorería. No
hace commit: corre dentro de la unidad de trabajo del caso de uso.
"""
from __future__ import annotations

from backend.shared.ids import new_uuid


class TreasuryCashDepositGateway:
    def __init__(self, connection) -> None:
        self._connection = connection

    def _one(self, sql: str, params: tuple):
        cursor = self._connection.execute(sql, params)
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(zip((item[0] for item in cursor.description), row))

    def get(self, deposit_id: str):
        return self._one(
            "SELECT id,branch_id,amount,prepared_by,handover_id,status"
            " FROM cash_deposit_preparations WHERE id=?", (deposit_id,))

    def find_confirmation(self, deposit_id: str):
        return self._one("SELECT * FROM cash_deposit_confirmations WHERE deposit_id=?",
                         (deposit_id,))

    def add_confirmation(self, *, deposit_id: str, branch_id: str, amount: str,
                         ticket_reference: str, confirmed_by: str, operation_id: str,
                         confirmed_at: str) -> str:
        confirmation_id = new_uuid()
        self._connection.execute(
            """INSERT INTO cash_deposit_confirmations
            (id,deposit_id,branch_id,amount,ticket_reference,confirmed_by,operation_id,
             confirmed_at)
            VALUES(?,?,?,?,?,?,?,?)""",
            (confirmation_id, deposit_id, branch_id, amount, ticket_reference, confirmed_by,
             operation_id, confirmed_at))
        return confirmation_id
