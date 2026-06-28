# core/services/finance/accounts_receivable_service.py — SPJ ERP v13.4
"""
AccountsReceivableService — Cuentas por Cobrar (CxC).

Extraído de FinanceService (FASE 5 auditoría).
FinanceService conserva métodos públicos como wrappers legacy que delegan aquí.

Responsabilidades:
  - listar()          — CxC pendientes/parciales/vencidas con aging
  - summary()         — Totales y conteo de vencidas
  - crear_cxc()       — Alta de CxC + asiento doble entrada + commit
  - cobrar_cxc()      — Cobro parcial/total + asiento + commit

Nota sobre tabla canónica:
  Este servicio opera sobre `accounts_receivable` (tabla FinanceService).
  `cuentas_por_cobrar` (usada por CreditSaleFinanceHandler) es diferente.
  Ver docs/architecture/FINANCE_CANONICAL_TABLES.md para el análisis de consolidación.

Reglas de atomicidad:
  - crear_cxc y cobrar_cxc hacen commit propio (operaciones autónomas).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Dict, List, Optional

logger = logging.getLogger("spj.finance.accounts_receivable")


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


class AccountsReceivableService:
    """Servicio canónico de Cuentas por Cobrar."""

    def __init__(self, db, ledger_service=None):
        from core.db.connection import wrap
        self._db     = wrap(db)
        self._ledger = ledger_service

    def _registrar_asiento(self, **kwargs) -> int:
        if self._ledger and hasattr(self._ledger, "registrar_asiento"):
            return self._ledger.registrar_asiento(**kwargs)
        return 0

    # ──────────────────────────────────────────────────────────────────────────

    def listar(self, status_filter: Optional[str] = None) -> List[Dict]:
        """Lista CxC con aging y datos de cliente."""
        conds = ["ar.status IN ('pendiente','parcial','vencido')"]
        params: list = []
        if status_filter:
            conds = [f"ar.status = ?"]
            params.append(status_filter)

        where = "WHERE " + " AND ".join(conds)
        try:
            rows = self._db.fetchall(
                f"""SELECT ar.*,
                           COALESCE(c.nombre,'') || ' ' || COALESCE(c.apellido_paterno,'')
                               AS cliente_nombre,
                           COALESCE(c.telefono,'') AS cliente_telefono
                    FROM accounts_receivable ar
                    LEFT JOIN clientes c ON c.id = ar.cliente_id
                    {where}
                    ORDER BY COALESCE(ar.due_date,'9999-12-31'), ar.created_at DESC""",
                params,
            )
        except Exception as exc:
            logger.warning("AccountsReceivableService.listar: %s", exc)
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
        """Totales y conteo de vencidas."""
        try:
            row = self._db.fetchone("""
                SELECT
                    COALESCE(SUM(balance),0) AS total,
                    COUNT(*) AS count,
                    COUNT(CASE WHEN due_date IS NOT NULL AND due_date < date('now')
                               THEN 1 END) AS vencidas
                FROM accounts_receivable
                WHERE status IN ('pendiente','parcial','vencido')
            """)
            return dict(row) if row else {}
        except Exception:
            return {}

    def crear_cxc(
        self,
        cliente_id: Optional[int],
        concepto: str,
        amount: float,
        due_date: Optional[str] = None,
        venta_id: Optional[int] = None,
        usuario: str = "Sistema",
    ) -> int:
        """
        Crea CxC en accounts_receivable, registra asiento y hace commit.

        Retorna ar_id del registro creado.
        """
        from datetime import datetime
        from backend.shared.ids import new_uuid
        folio = f"CXC-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        ar_id = new_uuid()  # identidad UUIDv7 explícita (REGLA CERO)
        self._db.execute(
            """INSERT INTO accounts_receivable
                   (id, folio, cliente_id, venta_id, concepto, amount, balance,
                    due_date, status, tipo, usuario)
               VALUES (?,?,?,?,?,?,?,?,'pendiente','manual',?)""",
            (ar_id, folio, cliente_id, venta_id, concepto, amount, amount, due_date, usuario),
        )
        self._registrar_asiento(
            debe="cuentas_por_cobrar",
            haber="ventas_credito",
            concepto=f"CXC {folio}: {concepto}",
            monto=float(amount or 0),
            modulo="finanzas",
            referencia_id=ar_id,
            evento="CXC_CREADA",
            metadata={"folio": folio, "cliente_id": cliente_id, "venta_id": venta_id},
        )
        try:
            self._db.commit()
        except Exception:
            pass
        return ar_id

    def cobrar_cxc(
        self,
        ar_id: int,
        monto: float,
        metodo_pago: str = "efectivo",
        usuario: str = "Sistema",
        notas: Optional[str] = None,
    ) -> Dict:
        """
        Registra cobro de CxC, actualiza balance/status y hace commit.

        Retorna dict con nuevo_balance y nuevo_status.
        """
        row = self._db.fetchone(
            "SELECT balance FROM accounts_receivable WHERE id=?", (ar_id,)
        )
        if not row:
            raise ValueError(f"CXC {ar_id} no encontrada")
        balance = float(row["balance"])
        if monto > balance:
            monto = balance

        nuevo_balance = round(balance - monto, 2)
        nuevo_status  = "pagado" if nuevo_balance <= 0 else "parcial"

        self._db.execute(
            """UPDATE accounts_receivable
               SET balance=?, status=?, updated_at=datetime('now')
               WHERE id=?""",
            (nuevo_balance, nuevo_status, ar_id),
        )
        from backend.shared.ids import new_uuid
        self._db.execute(
            "INSERT INTO ar_payments (id, ar_id, monto, metodo_pago, usuario, notas) VALUES (?,?,?,?,?,?)",
            (new_uuid(), ar_id, monto, metodo_pago, usuario, notas),
        )
        self._registrar_asiento(
            debe="caja_bancos",
            haber="cuentas_por_cobrar",
            concepto=f"Cobro CXC #{ar_id}",
            monto=float(monto or 0),
            modulo="finanzas",
            referencia_id=ar_id,
            evento="CXC_COBRADA",
            metadata={"metodo_pago": metodo_pago},
        )
        try:
            self._db.commit()
        except Exception:
            pass
        return {"nuevo_balance": nuevo_balance, "nuevo_status": nuevo_status}
