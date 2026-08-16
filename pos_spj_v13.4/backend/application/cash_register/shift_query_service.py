"""Read model for CASH-7 shift opening and lifecycle pages."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.blind_count_visibility import shift_has_open_blind_count
from backend.application.cash_register.permissions import CashPermissions


@dataclass(frozen=True, slots=True)
class CashShiftRow:
    id: str
    register_name: str
    drawer_name: str
    terminal_name: str
    cashier_user_id: str
    cashier_name: str
    status: str
    opening_amount: Decimal
    expected_cash: Decimal | None
    opened_at: str


@dataclass(frozen=True, slots=True)
class CashShiftList:
    active_count: int
    rows: tuple[CashShiftRow, ...]


class CashShiftQueryService:
    """Read-only shift projection consumed by the desktop UI."""

    def __init__(self, connection, authorization: CashAuthorizationPolicy) -> None:
        self._connection = connection
        self._authorization = authorization

    def list_recent(
        self,
        *,
        branch_id: str,
        requester_user_id: str,
        limit: int = 100,
    ) -> CashShiftList:
        self._authorization.require(
            user_id=requester_user_id,
            permission_code=CashPermissions.SHIFT_VIEW,
            branch_id=branch_id,
        )
        safe_limit = max(1, min(int(limit or 100), 500))
        users_join = ""
        cashier_expr = "s.cashier_user_id"
        cashier_group = "s.cashier_user_id"
        if self._has_table("usuarios"):
            users_join = "LEFT JOIN usuarios u ON u.id=s.cashier_user_id"
            cashier_expr = "COALESCE(u.nombre,u.usuario,s.cashier_user_id)"
            cashier_group = "s.cashier_user_id,u.nombre,u.usuario"
        cursor = self._connection.execute(
            f"""SELECT s.id,
                      COALESCE(r.name,''),
                      COALESCE(d.name,''),
                      COALESCE(t.name,''),
                      s.cashier_user_id,
                      {cashier_expr},
                      s.status,
                      s.opening_amount,
                      COALESCE(SUM(CASE l.direction
                          WHEN 'INFLOW' THEN CAST(l.amount AS NUMERIC)
                          ELSE -CAST(l.amount AS NUMERIC) END),0),
                      s.opened_at
               FROM cash_shifts s
               JOIN cash_registers r ON r.id=s.register_id
               JOIN cash_drawers d ON d.id=s.drawer_id
               JOIN pos_terminals t ON t.id=s.terminal_id
               {users_join}
               LEFT JOIN cash_ledger_entries l ON l.shift_id=s.id
               WHERE s.branch_id=?
               GROUP BY s.id,r.name,d.name,t.name,{cashier_group},s.status,
                        s.opening_amount,s.opened_at
               ORDER BY CASE s.status
                   WHEN 'OPEN' THEN 0
                   WHEN 'SUSPENDED' THEN 1
                   WHEN 'CLOSING' THEN 2
                   ELSE 3 END,
                   s.opened_at DESC
               LIMIT ?""",
            (branch_id, safe_limit),
        )
        rows = tuple(self._row_from_record(row) for row in cursor.fetchall())
        active_count = sum(1 for row in rows if row.status in {"OPEN", "SUSPENDED", "CLOSING"})
        return CashShiftList(active_count=active_count, rows=rows)

    def _row_from_record(self, row) -> CashShiftRow:
        shift_id = str(row[0])
        expected_cash = (
            None
            if shift_has_open_blind_count(self._connection, shift_id)
            else Decimal(str(row[8] or "0"))
        )
        return CashShiftRow(
            id=shift_id,
            register_name=str(row[1] or ""),
            drawer_name=str(row[2] or ""),
            terminal_name=str(row[3] or ""),
            cashier_user_id=str(row[4] or ""),
            cashier_name=str(row[5] or ""),
            status=str(row[6] or ""),
            opening_amount=Decimal(str(row[7] or "0")),
            expected_cash=expected_cash,
            opened_at=str(row[9] or ""),
        )

    def _has_table(self, name: str) -> bool:
        try:
            row = self._connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (name,),
            ).fetchone()
        except Exception:
            return False
        return bool(row)
