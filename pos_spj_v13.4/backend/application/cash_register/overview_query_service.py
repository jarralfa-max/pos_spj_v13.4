"""Operational BI/read model for CASH-22 Caja dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.blind_count_visibility import branch_has_open_blind_count
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
    next_action: str = ""


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
        # Auditoría CJA-01: fondo inicial, diferencias, montos de entrega y el
        # efectivo esperado son importes sensibles (antes los veía cualquiera con
        # acceso a Caja); y nunca mientras haya un arqueo ciego abierto.
        from backend.application.cash_register.amount_visibility import CashAmountVisibility
        amounts = CashAmountVisibility(self._connection, self._authorization)             .branch_amounts_visible(requester_user_id=requester_user_id, branch_id=branch_id)
        active = self._active_shifts(branch_id, amounts)
        closures = self._pending_closures(branch_id)
        differences = self._pending_differences(branch_id, amounts)
        handovers = self._pending_handovers(branch_id, amounts)
        terminals = self._terminal_alerts(branch_id)
        expected_hidden = not amounts
        expected = None if expected_hidden else self._expected_cash(branch_id)
        kpis = (
            CashOverviewKpi("active_shifts", "Turnos activos", str(len(active)), len(active)),
            CashOverviewKpi(
                "expected_cash",
                "Efectivo esperado",
                (("Oculto por arqueo" if branch_has_open_blind_count(self._connection, branch_id)
                  else "Oculto") if expected_hidden else f"${expected:.2f}"),
                expected,
            ),
            CashOverviewKpi("safe_drops", "Retiros pendientes", str(len(handovers)), len(handovers)),
            CashOverviewKpi("differences", "Diferencias pendientes", str(len(differences)), len(differences)),
            CashOverviewKpi("closures", "Cierres pendientes", str(len(closures)), len(closures)),
            CashOverviewKpi("terminals", "Terminales con alerta", str(len(terminals)), len(terminals)),
            self._finance_backlog_kpi(branch_id),
            self._unsettled_sales_kpi(branch_id),
        )
        return CashOverviewDTO(
            kpis=kpis,
            active_shifts=active,
            pending_closures=closures,
            pending_differences=differences,
            pending_handovers=handovers,
            terminal_alerts=terminals,
            freshness=self._freshness(),
            next_action=self._next_action(
                active=active,
                closures=closures,
                differences=differences,
                handovers=handovers,
                terminals=terminals,
            ),
        )

    def _finance_backlog_kpi(self, branch_id: str) -> CashOverviewKpi:
        """Auditoría CJA-04: lo que Caja todavía no entrega a Finanzas (Corte Z,
        entregas de valores) — pendiente o agotados sus reintentos — y desde
        cuándo. Antes nadie lo veía."""
        try:
            row = self._connection.execute(
                """SELECT SUM(CASE WHEN status IN ('PENDING','FAILED','PROCESSING') THEN 1 ELSE 0 END),
                          SUM(CASE WHEN status='DEAD_LETTER' THEN 1 ELSE 0 END),
                          MIN(CASE WHEN status<>'DISPATCHED' THEN created_at END)
                   FROM cash_outbox
                   WHERE status<>'DISPATCHED' AND json_extract(payload_json,'$.branch_id')=?""",
                (branch_id,)).fetchone()
        except Exception:  # noqa: BLE001 - base sin outbox de Caja
            row = (0, 0, None)
        pending, dead, oldest = int(row[0] or 0), int(row[1] or 0), row[2]
        total = pending + dead
        if not total:
            text = "Al día"
        else:
            text = f"{total} pendiente(s)"
            if dead:
                text += f", {dead} sin reintentos"
            if oldest:
                text += f" · desde {str(oldest)[:16].replace('T', ' ')}"
        return CashOverviewKpi("finance_backlog", "Envíos a Finanzas", text, total)

    def _unsettled_sales_kpi(self, branch_id: str) -> CashOverviewKpi:
        """Auditoría CJA-03: conciliación Ventas ↔ Caja. Desde 2026-10-15 el cobro
        del mostrador registra Caja en su misma transacción, así que debe ser 0;
        si no lo es (ventas de antes, o Pedidos que liquida el repartidor), aquí
        se ve en vez de perderse."""
        try:
            row = self._connection.execute(
                """SELECT COUNT(*) FROM sales s
                   WHERE s.branch_id=? AND s.channel='POS'
                     AND s.status IN ('COMPLETED','RETURNED_PARTIALLY','RETURNED_FULLY')
                     AND EXISTS (SELECT 1 FROM sale_payments p WHERE p.sale_id=s.id)
                     AND NOT EXISTS (SELECT 1 FROM payment_records r WHERE r.sale_id=s.id)""",
                (branch_id,)).fetchone()
        except Exception:  # noqa: BLE001 - base sin Ventas canónicas o sin liquidaciones
            row = (0,)
        count = int(row[0] or 0)
        return CashOverviewKpi("unsettled_sales", "Ventas sin registro en Caja",
                               "Ninguna" if not count else f"{count} venta(s)", count)

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

    def _active_shifts(self, branch_id: str, amounts: bool = True) -> tuple[CashOverviewRow, ...]:
        detail = "'Fondo inicial $'||s.opening_amount" if amounts else "'Turno activo'"
        return self._fetch_rows(
            f"""SELECT s.id,r.name,s.status,{detail},s.opened_at
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

    def _pending_differences(self, branch_id: str, amounts: bool = True) -> tuple[CashOverviewRow, ...]:
        importe = "'Importe $'||amount||' - '||" if amounts else ""
        return self._fetch_rows(
            f"""SELECT id,
                      CASE classification WHEN 'SHORTAGE' THEN 'Faltante' WHEN 'OVERAGE' THEN 'Sobrante' ELSE classification END,
                      status,
                      {importe}
                      CASE severity WHEN 'CRITICAL' THEN 'critica' WHEN 'REVIEW' THEN 'requiere revision' ELSE 'dentro de tolerancia' END,
                      ''
            FROM cash_differences
            WHERE branch_id=? AND status<>'RESOLVED'
            ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'REVIEW' THEN 1 ELSE 2 END,
                     recurrence_count DESC LIMIT 10""",
            (branch_id,),
        )

    def _pending_handovers(self, branch_id: str, amounts: bool = True) -> tuple[CashOverviewRow, ...]:
        detail = "'Monto preparado $'||amount" if amounts else "'Pendiente de entrega'"
        return self._fetch_rows(
            f"""SELECT id,'Entrega de valores',status,{detail},prepared_at
            FROM cash_handovers
            WHERE branch_id=? AND status IN ('PREPARED','DELIVERED','DISPUTED')
            ORDER BY prepared_at DESC LIMIT 10""",
            (branch_id,),
        )

    def _terminal_alerts(self, branch_id: str) -> tuple[CashOverviewRow, ...]:
        return self._fetch_rows(
            """SELECT id,name,status,'Revisar disponibilidad antes de cobrar con tarjeta',updated_at
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

    def _next_action(
        self,
        *,
        active: tuple[CashOverviewRow, ...],
        closures: tuple[CashOverviewRow, ...],
        differences: tuple[CashOverviewRow, ...],
        handovers: tuple[CashOverviewRow, ...],
        terminals: tuple[CashOverviewRow, ...],
    ) -> str:
        if closures:
            return "Hay turnos en cierre: confirma el conteo y genera el Corte Z."
        if differences:
            return "Hay diferencias pendientes: revisa explicacion, evidencia y segregacion."
        if handovers:
            return "Hay entregas de valores pendientes: confirma entrega o recepcion."
        if terminals:
            return "Hay terminales con alerta: diagnostica hardware antes de operar."
        if active:
            return "Operacion normal: monitorea movimientos y prepara retiro si excede politica."
        return "No hay turno activo: abre un turno para iniciar operacion de caja."
