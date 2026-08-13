"""Operational BI/read model for CASH-22 Caja dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import CashPermissions


@dataclass(frozen=True, slots=True)
class CashOverviewKpi:
    key: str
    label: str
    value: str
    numeric_value: int | Decimal | None = None


@dataclass(frozen=True, slots=True)
class CashOverviewRow:
    id: str
    label: str
    status: str
    detail: str
    occurred_at: str


@dataclass(frozen=True, slots=True)
class CashOverviewDTO:
    kpis: tuple[CashOverviewKpi, ...]
    active_shifts: tuple[CashOverviewRow, ...]
    pending_closures: tuple[CashOverviewRow, ...]
    pending_differences: tuple[CashOverviewRow, ...]
    pending_handovers: tuple[CashOverviewRow, ...]
    terminal_alerts: tuple[CashOverviewRow, ...]
    freshness: str


class CashOverviewQueryService:
    """Read-only dashboard service; UI must not aggregate operational Caja data."""

    def __init__(self, connection, authorization: CashAuthorizationPolicy) -> None:
        self._connection = connection
        self._authorization = authorization

    def dashboard(self, *, branch_id: str, requester_user_id: str) -> CashOverviewDTO:
        self._authorization.require(
            user_id=requester_user_id,
            permission_code=CashPermissions.ACCESS,
            branch_id=branch_id,
        )
        active = self._active_shifts(branch_id)
        closures = self._pending_closures(branch_id)
        differences = self._pending_differences(branch_id)
        handovers = self._pending_handovers(branch_id)
        terminals = self._terminal_alerts(branch_id)
        expected = self._expected_cash(branch_id)
        kpis = (
            CashOverviewKpi("active_shifts", "Turnos activos", str(len(active)), len(active)),
            CashOverviewKpi("expected_cash", "Efectivo esperado", f"${expected:.2f}", expected),
            CashOverviewKpi("safe_drops", "Retiros pendientes", str(len(handovers)), len(handovers)),
            CashOverviewKpi("differences", "Diferencias pendientes", str(len(differences)), len(differences)),
            CashOverviewKpi("closures", "Cierres pendientes", str(len(closures)), len(closures)),
            CashOverviewKpi("terminals", "Terminales con alerta", str(len(terminals)), len(terminals)),
        )
        return CashOverviewDTO(
            kpis=kpis,
            active_shifts=active,
            pending_closures=closures,
            pending_differences=differences,
            pending_handovers=handovers,
            terminal_alerts=terminals,
            freshness=self._freshness(),
        )

    def _fetch_rows(self, sql: str, params: tuple) -> tuple[CashOverviewRow, ...]:
        cursor = self._connection.execute(sql, params)
        return tuple(
            CashOverviewRow(
                id=str(row[0]),
                label=str(row[1]),
                status=str(row[2]),
                detail=str(row[3] or ""),
                occurred_at=str(row[4] or ""),
            )
            for row in cursor.fetchall()
        )

    def _active_shifts(self, branch_id: str) -> tuple[CashOverviewRow, ...]:
        return self._fetch_rows(
            """SELECT s.id,r.name,s.status,
                      'Cajero '||substr(s.cashier_user_id,1,8)||' · apertura '||s.opening_amount,
                      s.opened_at
            FROM cash_shifts s JOIN cash_registers r ON r.id=s.register_id
            WHERE s.branch_id=? AND s.status IN ('OPEN','SUSPENDED','CLOSING')
            ORDER BY s.opened_at DESC LIMIT 10""",
            (branch_id,),
        )

    def _pending_closures(self, branch_id: str) -> tuple[CashOverviewRow, ...]:
        return self._fetch_rows(
            """SELECT s.id,r.name,s.status,'Turno en cierre sin Corte Z final',s.opened_at
            FROM cash_shifts s JOIN cash_registers r ON r.id=s.register_id
            WHERE s.branch_id=? AND s.status='CLOSING'
            ORDER BY s.opened_at LIMIT 10""",
            (branch_id,),
        )

    def _pending_differences(self, branch_id: str) -> tuple[CashOverviewRow, ...]:
        return self._fetch_rows(
            """SELECT id,classification,status,'Importe '||amount||' · severidad '||severity,''
            FROM cash_differences
            WHERE branch_id=? AND status<>'RESOLVED'
            ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'REVIEW' THEN 1 ELSE 2 END,
                     recurrence_count DESC LIMIT 10""",
            (branch_id,),
        )

    def _pending_handovers(self, branch_id: str) -> tuple[CashOverviewRow, ...]:
        return self._fetch_rows(
            """SELECT id,'Entrega de valores',status,'Importe '||amount,prepared_at
            FROM cash_handovers
            WHERE branch_id=? AND status IN ('PREPARED','DELIVERED','DISPUTED')
            ORDER BY prepared_at DESC LIMIT 10""",
            (branch_id,),
        )

    def _terminal_alerts(self, branch_id: str) -> tuple[CashOverviewRow, ...]:
        return self._fetch_rows(
            """SELECT id,name,status,'Terminal POS requiere atencion',updated_at
            FROM pos_terminals
            WHERE branch_id=? AND status<>'ACTIVE'
            ORDER BY updated_at DESC LIMIT 10""",
            (branch_id,),
        )

    def _expected_cash(self, branch_id: str) -> Decimal:
        row = self._connection.execute(
            """SELECT COALESCE(SUM(CASE direction
                WHEN 'INFLOW' THEN CAST(amount AS NUMERIC)
                ELSE -CAST(amount AS NUMERIC) END),0)
            FROM cash_ledger_entries
            WHERE branch_id=? AND shift_id IN (
                SELECT id FROM cash_shifts
                WHERE branch_id=? AND status IN ('OPEN','SUSPENDED','CLOSING')
            )""",
            (branch_id, branch_id),
        ).fetchone()
        return Decimal(str(row[0] if row else "0"))

    def _freshness(self) -> str:
        row = self._connection.execute(
            """SELECT MAX(value) FROM (
                SELECT MAX(recorded_at) value FROM cash_ledger_entries
                UNION ALL SELECT MAX(prepared_at) FROM cash_handovers
                UNION ALL SELECT MAX(generated_at) FROM cash_cuts
                UNION ALL SELECT MAX(updated_at) FROM pos_terminals
            )"""
        ).fetchone()
        return str(row[0] or "")
