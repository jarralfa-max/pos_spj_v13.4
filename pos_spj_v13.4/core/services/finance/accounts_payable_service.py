# core/services/finance/accounts_payable_service.py — SPJ ERP v13.4
"""
AccountsPayableService — Cuentas por Pagar (CxP).

Extraído de FinanceService (FASE 5 auditoría).
FinanceService conserva métodos públicos como wrappers legacy que delegan aquí.

Responsabilidades:
  - listar()          — CxP pendientes/parciales con aging
  - summary()         — Totales y conteo de vencidas
  - crear_cxp()       — Alta de CxP + asiento doble entrada + commit
  - abonar_cxp()      — Abono parcial/total + asiento + commit
  - historial_pagos() — Historial de pagos a una CxP

Reglas de atomicidad:
  - crear_cxp y abonar_cxp hacen commit propio (operaciones autónomas).
  - Si se llaman dentro de un SAVEPOINT del caller, el SAVEPOINT queda comprometido.
    En ese caso el caller debe usar el método de FinanceService (wrapper legacy sin commit)
    y hacer su propio commit/release al finalizar la operación compuesta.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Dict, List, Optional

logger = logging.getLogger("spj.finance.accounts_payable")

# ── Aging helper ─────────────────────────────────────────────────────────────

def _aging(due_date_str: Optional[str]) -> str:
    if not due_date_str:
        return "corriente"
    try:
        due  = date.fromisoformat(str(due_date_str)[:10])
        days = (date.today() - due).days
        if days <= 0:  return "corriente"
        if days <= 30: return "1-30d"
        if days <= 60: return "31-60d"
        if days <= 90: return "61-90d"
        return "+90d"
    except Exception:
        return "corriente"


class AccountsPayableService:
    """Servicio canónico de Cuentas por Pagar."""

    def __init__(self, db, ledger_service=None):
        from core.db.connection import wrap
        self._db     = wrap(db)
        self._ledger = ledger_service  # GeneralLedgerService o FinanceService

    def _registrar_asiento(self, **kwargs) -> int:
        """Delega a ledger_service si está disponible, o usa FinanceService."""
        if self._ledger and hasattr(self._ledger, "registrar_asiento"):
            return self._ledger.registrar_asiento(**kwargs)
        return 0

    # ──────────────────────────────────────────────────────────────────────────

    def listar(
        self,
        status_filter: Optional[str] = None,
        supplier_id: Optional[int] = None,
    ) -> List[Dict]:
        """Lista CxP con aging, proveedor y totales."""
        conds = ["ap.status IN ('pendiente','parcial')"]
        params: list = []
        if status_filter:
            conds = [f"ap.status = ?"]
            params.append(status_filter)
        if supplier_id:
            conds.append("ap.supplier_id = ?")
            params.append(supplier_id)

        where = "WHERE " + " AND ".join(conds)
        try:
            rows = self._db.fetchall(
                f"""SELECT ap.*,
                           COALESCE(s.nombre,'—') AS supplier_nombre,
                           COALESCE(s.telefono,'') AS supplier_telefono
                    FROM accounts_payable ap
                    LEFT JOIN suppliers s ON s.id = ap.supplier_id
                    {where}
                    ORDER BY COALESCE(ap.due_date,'9999-12-31'), ap.created_at DESC""",
                params,
            )
        except Exception as exc:
            logger.warning("AccountsPayableService.listar: %s", exc)
            return []

        result = []
        for r in rows:
            d = dict(r)
            d["aging"]        = _aging(d.get("due_date"))
            d["dias_vencido"] = max(0, (
                date.today() - date.fromisoformat(str(d["due_date"])[:10])
            ).days) if d.get("due_date") else 0
            result.append(d)
        return result

    def summary(self) -> Dict:
        """Totales pendiente/parcial y conteo de vencidas."""
        try:
            row = self._db.fetchone("""
                SELECT
                    COALESCE(SUM(CASE WHEN status='pendiente' THEN balance END),0) AS pendiente,
                    COALESCE(SUM(CASE WHEN status='parcial'   THEN balance END),0) AS parcial,
                    COUNT(CASE WHEN status IN ('pendiente','parcial')
                               AND due_date IS NOT NULL AND due_date < date('now')
                               THEN 1 END) AS vencidas
                FROM accounts_payable
            """)
            return dict(row) if row else {}
        except Exception:
            return {}

    def crear_cxp(
        self,
        supplier_id: Optional[int],
        concepto: str,
        amount: float,
        due_date: Optional[str] = None,
        tipo: str = "factura",
        referencia: Optional[str] = None,
        ref_type: str = "manual",
        usuario: str = "Sistema",
        notas: Optional[str] = None,
    ) -> int:
        """
        Crea CxP, registra asiento doble entrada y hace commit.

        Retorna ap_id del registro creado.
        """
        from datetime import datetime
        from backend.shared.ids import new_uuid
        folio = f"CXP-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        ap_id = new_uuid()  # identidad UUIDv7 explícita (REGLA CERO)
        self._db.execute(
            """INSERT INTO accounts_payable
                   (id, folio, supplier_id, concepto, amount, balance,
                    due_date, status, tipo, referencia, ref_type, usuario, notas)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ap_id, folio, supplier_id, concepto, amount, amount,
             due_date, "pendiente", tipo, referencia, ref_type, usuario, notas),
        )
        self._registrar_asiento(
            debe="gastos_operativos",
            haber="cuentas_por_pagar",
            concepto=f"CXP {folio}: {concepto}",
            monto=float(amount or 0),
            modulo="finanzas",
            referencia_id=ap_id,
            evento="CXP_CREADA",
            metadata={"folio": folio, "supplier_id": supplier_id, "tipo": tipo},
        )
        try:
            self._db.commit()
        except Exception:
            pass
        return ap_id

    def abonar_cxp(
        self,
        ap_id: int,
        monto: float,
        metodo_pago: str = "efectivo",
        usuario: str = "Sistema",
        notas: Optional[str] = None,
    ) -> Dict:
        """
        Registra abono a CxP, actualiza balance/status y hace commit.

        Retorna dict con nuevo_balance y nuevo_status.
        """
        row = self._db.fetchone(
            "SELECT balance, status FROM accounts_payable WHERE id=?", (ap_id,)
        )
        if not row:
            raise ValueError(f"CXP {ap_id} no encontrada")
        balance = float(row["balance"])
        if monto > balance:
            monto = balance

        nuevo_balance = round(balance - monto, 2)
        nuevo_status  = "pagado" if nuevo_balance <= 0 else "parcial"

        self._db.execute(
            """UPDATE accounts_payable
               SET balance=?, status=?, updated_at=datetime('now')
               WHERE id=?""",
            (nuevo_balance, nuevo_status, ap_id),
        )
        from backend.shared.ids import new_uuid
        self._db.execute(
            "INSERT INTO ap_payments (id, ap_id, monto, metodo_pago, usuario, notas) VALUES (?,?,?,?,?,?)",
            (new_uuid(), ap_id, monto, metodo_pago, usuario, notas),
        )
        self._registrar_asiento(
            debe="cuentas_por_pagar",
            haber="caja_bancos",
            concepto=f"Pago CXP #{ap_id}",
            monto=float(monto or 0),
            modulo="finanzas",
            referencia_id=ap_id,
            evento="CXP_ABONADA",
            metadata={"metodo_pago": metodo_pago},
        )
        try:
            self._db.commit()
        except Exception:
            pass
        return {"nuevo_balance": nuevo_balance, "nuevo_status": nuevo_status}

    def historial_pagos(self, ap_id: int) -> List[Dict]:
        """Historial de abonos a una CxP."""
        try:
            rows = self._db.fetchall(
                "SELECT * FROM ap_payments WHERE ap_id=? ORDER BY fecha DESC", (ap_id,)
            )
            return [dict(r) for r in rows]
        except Exception:
            return []
