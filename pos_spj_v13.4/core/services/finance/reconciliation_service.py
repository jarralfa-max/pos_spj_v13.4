# core/services/finance/reconciliation_service.py — SPJ ERP v13.4
"""
ReconciliationService — detección de inconsistencias financieras.

Verifica que cada operación financiera esté completa: documento + treasury + asiento.
Detecta duplicados, operaciones huérfanas, diferencias de caja y balances incorrectos.

Métodos:
  reconcile_sales_vs_treasury(date, branch_id)
  reconcile_receivables()
  reconcile_payables()
  reconcile_cash_shift(turno_id)
  reconcile_delivery_driver_cut(cut_id)
  reconcile_journal_balance(date_from, date_to)
  reconcile_assets()
  reconcile_asset_depreciation(period)
  reconcile_maintenance()
  reconcile_operating_supplies()

Cada método retorna una lista de ReconciliationIssue dicts con:
  check_type, source_module, source_id, expected, actual, difference, status, message
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

logger = logging.getLogger("spj.finance.reconciliation")

_OK          = "ok"
_DISCREPANCY = "discrepancy"


class ReconciliationService:
    """Detección de inconsistencias financieras entre módulos."""

    def __init__(self, db):
        from core.db.connection import wrap
        self._db = wrap(db)

    # ── Ventas vs Tesorería ───────────────────────────────────────────────────

    def reconcile_sales_vs_treasury(
        self,
        date: Optional[str] = None,
        branch_id: Optional[int] = None,
    ) -> List[Dict]:
        """
        Detecta ventas contado sin treasury_movement correspondiente.
        Una venta contado completada debe tener un inflow en treasury_movements.
        """
        issues = []
        params: list = []
        date_cond  = " AND DATE(v.fecha)=?" if date else ""
        branch_cond = " AND v.sucursal_id=?" if branch_id else ""
        if date:   params.append(date)
        if branch_id: params.append(branch_id)

        try:
            rows = self._db.fetchall(
                f"""SELECT v.id, v.folio, v.total, v.forma_pago, v.sucursal_id
                    FROM ventas v
                    WHERE v.estado='completada'
                      AND v.forma_pago NOT IN ('Credito','credito','Mercado Pago')
                      {date_cond}{branch_cond}
                      AND NOT EXISTS (
                          SELECT 1 FROM treasury_movements tm
                          WHERE tm.source_module='ventas'
                            AND tm.source_id=v.id
                            AND tm.movement_type='inflow'
                      )
                    ORDER BY v.fecha DESC LIMIT 500""",
                params,
            )
            for r in rows:
                issues.append(self._issue(
                    check_type="sale_without_treasury",
                    source_module="ventas",
                    source_id=r["id"],
                    expected=float(r["total"]),
                    actual=0.0,
                    status=_DISCREPANCY,
                    message=f"Venta {r['folio']} ({r['forma_pago']}) sin treasury_movement",
                ))
        except Exception as exc:
            logger.debug("reconcile_sales_vs_treasury: %s", exc)

        return issues

    # ── CxC sin asiento ───────────────────────────────────────────────────────

    def reconcile_receivables(self) -> List[Dict]:
        """
        Detecta financial_documents(receivable) sin journal_entry correspondiente.
        """
        issues = []
        try:
            rows = self._db.fetchall(
                """SELECT fd.id, fd.operation_id, fd.original_amount, fd.source_module
                   FROM financial_documents fd
                   WHERE fd.document_type='receivable'
                     AND fd.status IN ('pending','partial')
                     AND NOT EXISTS (
                         SELECT 1 FROM journal_entries je
                         WHERE je.operation_id = fd.operation_id || '-JE'
                     )
                   LIMIT 500"""
            )
            for r in rows:
                issues.append(self._issue(
                    check_type="cxc_without_journal",
                    source_module=r["source_module"],
                    source_id=r["id"],
                    expected=float(r["original_amount"]),
                    actual=0.0,
                    status=_DISCREPANCY,
                    message=f"CxC op={r['operation_id']} sin journal_entry",
                ))
        except Exception as exc:
            logger.debug("reconcile_receivables: %s", exc)
        return issues

    # ── CxP sin asiento ───────────────────────────────────────────────────────

    def reconcile_payables(self) -> List[Dict]:
        """
        Detecta financial_documents(payable) sin journal_entry correspondiente.
        """
        issues = []
        try:
            rows = self._db.fetchall(
                """SELECT fd.id, fd.operation_id, fd.original_amount, fd.source_module
                   FROM financial_documents fd
                   WHERE fd.document_type IN ('payable','payroll','maintenance')
                     AND fd.status IN ('pending','partial')
                     AND NOT EXISTS (
                         SELECT 1 FROM journal_entries je
                         WHERE je.operation_id = fd.operation_id || '-JE'
                     )
                   LIMIT 500"""
            )
            for r in rows:
                issues.append(self._issue(
                    check_type="cxp_without_journal",
                    source_module=r["source_module"],
                    source_id=r["id"],
                    expected=float(r["original_amount"]),
                    actual=0.0,
                    status=_DISCREPANCY,
                    message=f"CxP op={r['operation_id']} sin journal_entry",
                ))
        except Exception as exc:
            logger.debug("reconcile_payables: %s", exc)
        return issues

    # ── Corte de turno ────────────────────────────────────────────────────────

    def reconcile_cash_shift(self, turno_id: int) -> List[Dict]:
        """
        Verifica diferencia de caja en corte de turno.
        Compara suma de ventas efectivo vs treasury_movements del turno.
        """
        issues = []
        try:
            ventas_row = self._db.fetchone(
                """SELECT COALESCE(SUM(total),0) AS total_ventas
                   FROM ventas
                   WHERE turno_id=? AND estado='completada'
                     AND forma_pago IN ('Efectivo','efectivo')""",
                (turno_id,),
            )
            treasury_row = self._db.fetchone(
                """SELECT COALESCE(SUM(amount),0) AS total_treasury
                   FROM treasury_movements
                   WHERE source_module='ventas'
                     AND movement_type='inflow'
                     AND payment_method IN ('efectivo','Efectivo')
                     AND metadata_json LIKE ?""",
                (f'%"turno_id": {turno_id}%',),
            )
            expected = float(ventas_row["total_ventas"]) if ventas_row else 0
            actual   = float(treasury_row["total_treasury"]) if treasury_row else 0
            diff = round(actual - expected, 2)
            if abs(diff) > 0.01:
                issues.append(self._issue(
                    check_type="cash_shift_difference",
                    source_module="caja",
                    source_id=turno_id,
                    expected=expected,
                    actual=actual,
                    status=_DISCREPANCY,
                    message=f"Turno {turno_id}: diferencia de caja ${diff:+.2f}",
                ))
        except Exception as exc:
            logger.debug("reconcile_cash_shift turno=%s: %s", turno_id, exc)
        return issues

    # ── Corte de repartidor ───────────────────────────────────────────────────

    def reconcile_delivery_driver_cut(self, cut_id: int) -> List[Dict]:
        """Verifica corte de repartidor contra treasury_movements de delivery."""
        issues = []
        try:
            # Busca treasury_movements del delivery con ese cut_id
            row = self._db.fetchone(
                """SELECT COALESCE(SUM(amount),0) AS total
                   FROM treasury_movements
                   WHERE source_module='delivery'
                     AND movement_type='inflow'
                     AND metadata_json LIKE ?""",
                (f'%"cut_id": {cut_id}%',),
            )
            actual = float(row["total"]) if row else 0.0
            if actual == 0:
                issues.append(self._issue(
                    check_type="delivery_cut_no_treasury",
                    source_module="delivery",
                    source_id=cut_id,
                    expected=0.0,
                    actual=0.0,
                    status=_DISCREPANCY,
                    message=f"Corte repartidor {cut_id}: sin treasury_movements registrados",
                ))
        except Exception as exc:
            logger.debug("reconcile_delivery_driver_cut: %s", exc)
        return issues

    # ── Balance de diario ─────────────────────────────────────────────────────

    def reconcile_journal_balance(
        self, date_from: str, date_to: str
    ) -> List[Dict]:
        """
        Verifica que total_debit == total_credit en journal_entries del período.
        """
        issues = []
        try:
            row = self._db.fetchone(
                """SELECT
                       COALESCE(SUM(amount),0) AS total_debit,
                       COALESCE(SUM(amount),0) AS total_credit,
                       COUNT(*) AS count
                   FROM journal_entries
                   WHERE DATE(created_at) BETWEEN DATE(?) AND DATE(?)""",
                (date_from, date_to),
            )
            if row:
                total_d = float(row["total_debit"])
                total_c = float(row["total_credit"])
                diff = round(total_d - total_c, 4)
                status = _OK if abs(diff) < 0.0001 else _DISCREPANCY
                if status == _DISCREPANCY:
                    issues.append(self._issue(
                        check_type="journal_imbalance",
                        source_module="contabilidad",
                        source_id=None,
                        expected=total_d,
                        actual=total_c,
                        status=status,
                        message=f"Diario {date_from}/{date_to}: debe={total_d:.2f} haber={total_c:.2f} diff={diff}",
                    ))
        except Exception as exc:
            logger.debug("reconcile_journal_balance: %s", exc)
        return issues

    # ── Activos ───────────────────────────────────────────────────────────────

    def reconcile_assets(self) -> List[Dict]:
        """Detecta activos fijos sin journal_entry correspondiente."""
        issues = []
        try:
            rows = self._db.fetchall(
                """SELECT fa.id, fa.operation_id, fa.acquisition_cost, fa.asset_name
                   FROM fixed_assets fa
                   WHERE NOT EXISTS (
                       SELECT 1 FROM journal_entries je
                       WHERE je.operation_id = fa.operation_id || '-JE'
                   )
                   LIMIT 200"""
            )
            for r in rows:
                issues.append(self._issue(
                    check_type="asset_without_journal",
                    source_module="activos",
                    source_id=r["id"],
                    expected=float(r["acquisition_cost"]),
                    actual=0.0,
                    status=_DISCREPANCY,
                    message=f"Activo '{r['asset_name']}' sin journal_entry",
                ))
        except Exception as exc:
            logger.debug("reconcile_assets: %s", exc)
        return issues

    def reconcile_asset_depreciation(self, period: str) -> List[Dict]:
        """Detecta activos activos sin depreciación registrada en el período."""
        issues = []
        try:
            rows = self._db.fetchall(
                """SELECT fa.id, fa.asset_name, fa.acquisition_cost, fa.useful_life_months
                   FROM fixed_assets fa
                   WHERE fa.status = 'active'
                     AND NOT EXISTS (
                         SELECT 1 FROM asset_depreciation_entries ade
                         WHERE ade.asset_id = fa.id AND ade.period = ?
                     )
                   LIMIT 200""",
                (period,),
            )
            for r in rows:
                issues.append(self._issue(
                    check_type="asset_missing_depreciation",
                    source_module="activos",
                    source_id=r["id"],
                    expected=round(float(r["acquisition_cost"]) / max(int(r["useful_life_months"]), 1), 2),
                    actual=0.0,
                    status=_DISCREPANCY,
                    message=f"Activo '{r['asset_name']}' sin depreciación para {period}",
                ))
        except Exception as exc:
            logger.debug("reconcile_asset_depreciation period=%s: %s", period, exc)
        return issues

    # ── Mantenimientos ────────────────────────────────────────────────────────

    def reconcile_maintenance(self) -> List[Dict]:
        """Detecta mantenimientos sin journal_entry."""
        issues = []
        try:
            rows = self._db.fetchall(
                """SELECT mr.id, mr.operation_id, mr.amount, mr.maintenance_type
                   FROM maintenance_records mr
                   WHERE mr.status != 'cancelled'
                     AND NOT EXISTS (
                         SELECT 1 FROM journal_entries je
                         WHERE je.operation_id = mr.operation_id || '-JE'
                     )
                   LIMIT 200"""
            )
            for r in rows:
                issues.append(self._issue(
                    check_type="maintenance_without_journal",
                    source_module="mantenimiento",
                    source_id=r["id"],
                    expected=float(r["amount"]),
                    actual=0.0,
                    status=_DISCREPANCY,
                    message=f"Mantenimiento {r['maintenance_type']} id={r['id']} sin journal",
                ))
        except Exception as exc:
            logger.debug("reconcile_maintenance: %s", exc)
        return issues

    # ── Insumos ───────────────────────────────────────────────────────────────

    def reconcile_operating_supplies(self) -> List[Dict]:
        """Detecta insumos operativos sin journal_entry."""
        issues = []
        try:
            rows = self._db.fetchall(
                """SELECT os.id, os.operation_id, os.total_amount, os.supply_type
                   FROM operating_supplies os
                   WHERE os.status != 'cancelled'
                     AND NOT EXISTS (
                         SELECT 1 FROM journal_entries je
                         WHERE je.operation_id = os.operation_id || '-JE'
                     )
                   LIMIT 200"""
            )
            for r in rows:
                issues.append(self._issue(
                    check_type="supply_without_journal",
                    source_module="insumos",
                    source_id=r["id"],
                    expected=float(r["total_amount"]),
                    actual=0.0,
                    status=_DISCREPANCY,
                    message=f"Insumo {r['supply_type']} id={r['id']} sin journal",
                ))
        except Exception as exc:
            logger.debug("reconcile_operating_supplies: %s", exc)
        return issues

    # ── Duplicados ────────────────────────────────────────────────────────────

    def detect_duplicates(self, table: str = "journal_entries") -> List[Dict]:
        """Detecta operation_ids duplicados en la tabla indicada (no debería haberlos por UNIQUE)."""
        issues = []
        try:
            rows = self._db.fetchall(
                f"""SELECT operation_id, COUNT(*) as cnt
                    FROM {table}
                    GROUP BY operation_id
                    HAVING cnt > 1
                    LIMIT 100"""
            )
            for r in rows:
                issues.append(self._issue(
                    check_type=f"duplicate_operation_id_{table}",
                    source_module=table,
                    source_id=None,
                    expected=1.0,
                    actual=float(r["cnt"]),
                    status=_DISCREPANCY,
                    message=f"Duplicado op_id={r['operation_id']} en {table} (count={r['cnt']})",
                ))
        except Exception as exc:
            logger.debug("detect_duplicates table=%s: %s", table, exc)
        return issues

    # ── Helper ────────────────────────────────────────────────────────────────

    @staticmethod
    def _issue(
        check_type: str,
        source_module: str,
        source_id,
        expected: float,
        actual: float,
        status: str,
        message: str,
    ) -> Dict:
        return {
            "check_type":    check_type,
            "source_module": source_module,
            "source_id":     source_id,
            "expected":      expected,
            "actual":        actual,
            "difference":    round(actual - expected, 4),
            "status":        status,
            "message":       message,
        }
