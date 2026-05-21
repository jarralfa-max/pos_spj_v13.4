# core/services/finance/capital_service.py — SPJ ERP v13.4
"""
CapitalService — movimientos de capital y patrimonio.

Opera sobre `capital_movements` (migración 084).

Tipos de movimiento:
  injection        — inyección de capital por socio
  withdrawal       — retiro de capital por socio
  adjustment       — ajuste contable de patrimonio
  opening_balance  — balance inicial al arrancar

Reglas:
  - Idempotente por operation_id (UNIQUE).
  - inject() + withdraw() crean journal_entry y treasury_movement si se proveen los servicios.
  - get_summary() retorna capital_actual, total_inyectado, total_retirado.
  - NO hace commit — el caller controla la transacción.
"""
from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("spj.finance.capital")


class CapitalService:
    """Capital y patrimonio del negocio."""

    def __init__(self, db, journal_service=None, treasury_service=None):
        from core.db.connection import wrap
        self._db  = wrap(db)
        self._je  = journal_service
        self._tm  = treasury_service

    # ── Registro ──────────────────────────────────────────────────────────────

    def inject_capital(
        self,
        operation_id: str,
        amount: float,
        concept: str = "Inyección de capital",
        partner_name: str = "",
        partner_id: Optional[int] = None,
        payment_method: str = "efectivo",
        reference: str = "",
        branch_id: int = 1,
        user: str = "sistema",
        metadata: Optional[dict] = None,
    ) -> Dict:
        """
        Registra inyección de capital.

        treasury_movement: inflow (dinero entra al negocio)
        journal: debit=caja_o_banco / credit=capital_social

        Retorna: {movement_id, journal_id, capital_id}
        """
        return self._register(
            operation_id=operation_id,
            movement_type="injection",
            amount=amount,
            concept=concept,
            partner_name=partner_name,
            partner_id=partner_id,
            payment_method=payment_method,
            reference=reference,
            branch_id=branch_id,
            user=user,
            metadata=metadata,
            debit_account=self._cash_account(payment_method),
            credit_account="300-capital_social",
            event_type="CAPITAL_INJECTED",
            treasury_direction="inflow",
        )

    def withdraw_capital(
        self,
        operation_id: str,
        amount: float,
        concept: str = "Retiro de capital",
        partner_name: str = "",
        partner_id: Optional[int] = None,
        payment_method: str = "efectivo",
        reference: str = "",
        branch_id: int = 1,
        user: str = "sistema",
        metadata: Optional[dict] = None,
    ) -> Dict:
        """
        Registra retiro de capital.

        treasury_movement: outflow (dinero sale del negocio)
        journal: debit=retiros_socio / credit=caja_o_banco
        """
        return self._register(
            operation_id=operation_id,
            movement_type="withdrawal",
            amount=amount,
            concept=concept,
            partner_name=partner_name,
            partner_id=partner_id,
            payment_method=payment_method,
            reference=reference,
            branch_id=branch_id,
            user=user,
            metadata=metadata,
            debit_account="310-retiros_socio",
            credit_account=self._cash_account(payment_method),
            event_type="CAPITAL_WITHDRAWN",
            treasury_direction="outflow",
        )

    def set_opening_balance(
        self,
        operation_id: str,
        amount: float,
        concept: str = "Balance inicial",
        branch_id: int = 1,
        user: str = "sistema",
        metadata: Optional[dict] = None,
    ) -> Dict:
        """Registra balance inicial de capital (solo asiento, sin treasury)."""
        return self._register(
            operation_id=operation_id,
            movement_type="opening_balance",
            amount=amount,
            concept=concept,
            branch_id=branch_id,
            user=user,
            metadata=metadata,
            debit_account="110-caja",
            credit_account="300-capital_social",
            event_type="CAPITAL_OPENING_BALANCE",
            treasury_direction=None,
        )

    # ── Consultas ─────────────────────────────────────────────────────────────

    def get_summary(self, branch_id: Optional[int] = None) -> Dict:
        """
        Retorna resumen de capital.

        Returns:
            {capital_actual, total_inyectado, total_retirado, total_ajustes, movimientos}
        """
        try:
            where = "WHERE status='registered'"
            params: list = []
            if branch_id:
                where += " AND branch_id=?"
                params.append(branch_id)

            row = self._db.fetchone(
                f"""SELECT
                    COALESCE(SUM(CASE WHEN movement_type='injection'        THEN amount ELSE 0 END), 0) AS total_inyectado,
                    COALESCE(SUM(CASE WHEN movement_type='withdrawal'       THEN amount ELSE 0 END), 0) AS total_retirado,
                    COALESCE(SUM(CASE WHEN movement_type='opening_balance'  THEN amount ELSE 0 END), 0) AS balance_inicial,
                    COALESCE(SUM(CASE WHEN movement_type='adjustment'       THEN amount ELSE 0 END), 0) AS total_ajustes,
                    COUNT(*) AS total_movimientos
                FROM capital_movements {where}""",
                params,
            )
            if row:
                inyectado  = float(row["total_inyectado"])
                retirado   = float(row["total_retirado"])
                balance_i  = float(row["balance_inicial"])
                ajustes    = float(row["total_ajustes"])
                capital    = balance_i + inyectado - retirado + ajustes
                return {
                    "capital_actual":   round(capital, 2),
                    "total_inyectado":  round(inyectado, 2),
                    "total_retirado":   round(retirado, 2),
                    "balance_inicial":  round(balance_i, 2),
                    "total_ajustes":    round(ajustes, 2),
                    "total_movimientos": int(row["total_movimientos"]),
                }
        except Exception as exc:
            logger.debug("get_summary: %s", exc)
        return {
            "capital_actual": 0.0, "total_inyectado": 0.0,
            "total_retirado": 0.0, "balance_inicial": 0.0,
            "total_ajustes": 0.0, "total_movimientos": 0,
        }

    def get_history(
        self,
        branch_id: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Retorna historial de movimientos de capital."""
        try:
            where = "WHERE 1=1"
            params: list = []
            if branch_id:
                where += " AND branch_id=?"
                params.append(branch_id)
            params.append(limit)
            rows = self._db.fetchall(
                f"""SELECT * FROM capital_movements {where}
                    ORDER BY created_at DESC LIMIT ?""",
                params,
            )
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.debug("get_history: %s", exc)
            return []

    # ── Interno ───────────────────────────────────────────────────────────────

    def _register(
        self,
        operation_id: str,
        movement_type: str,
        amount: float,
        concept: str,
        debit_account: str,
        credit_account: str,
        event_type: str,
        treasury_direction: Optional[str],
        partner_name: str = "",
        partner_id: Optional[int] = None,
        payment_method: str = "efectivo",
        reference: str = "",
        branch_id: int = 1,
        user: str = "sistema",
        metadata: Optional[dict] = None,
    ) -> Dict:
        result = {"capital_id": 0, "journal_id": 0, "movement_id": 0}
        if not operation_id or amount <= 0:
            return result

        # Idempotencia
        try:
            existing = self._db.fetchone(
                "SELECT id FROM capital_movements WHERE operation_id=?", (operation_id,)
            )
            if existing:
                result["capital_id"] = int(existing["id"])
                return result
        except Exception as exc:
            logger.debug("capital_movements no disponible: %s", exc)
            return result

        # Asiento contable
        je_id = 0
        if self._je:
            try:
                je_id = self._je.post_entry(
                    operation_id=f"{operation_id}-JE",
                    event_type=event_type,
                    source_module="capital",
                    source_id=None,
                    debit_account=debit_account,
                    credit_account=credit_account,
                    amount=amount,
                    branch_id=branch_id,
                    user=user,
                    metadata={"concept": concept, "partner": partner_name,
                              **(metadata or {})},
                )
                result["journal_id"] = je_id
            except Exception as exc:
                logger.warning("capital journal_entry: %s", exc)

        # Movimiento de tesorería
        mov_id = 0
        if treasury_direction and self._tm:
            try:
                register_fn = (self._tm.register_inflow if treasury_direction == "inflow"
                               else self._tm.register_outflow)
                mov_id = register_fn(
                    operation_id=f"{operation_id}-TM",
                    amount=amount,
                    payment_method=payment_method,
                    source_module="capital",
                    source_id=None,
                    branch_id=branch_id,
                    user=user,
                    metadata={"concept": concept, "partner": partner_name},
                )
                result["movement_id"] = mov_id
            except Exception as exc:
                logger.warning("capital treasury_movement: %s", exc)

        # Insertar capital_movement
        try:
            cur = self._db.execute(
                """INSERT INTO capital_movements
                       (movement_type, amount, concept, partner_name, partner_id,
                        payment_method, reference, branch_id, user, status,
                        operation_id, journal_entry_id, treasury_movement_id, metadata_json)
                   VALUES (?,?,?,?,?,?,?,?,?,'registered',?,?,?,?)""",
                (
                    movement_type, float(amount), concept,
                    partner_name, partner_id,
                    payment_method, reference,
                    branch_id, user, operation_id,
                    je_id or None, mov_id or None,
                    json.dumps(metadata or {}, ensure_ascii=False, default=str),
                ),
            )
            result["capital_id"] = cur.lastrowid or 0
        except Exception as exc:
            logger.warning("capital_movements INSERT op=%s: %s", operation_id, exc)

        return result

    @staticmethod
    def _cash_account(payment_method: str) -> str:
        _MAP = {
            "efectivo": "110-caja", "Efectivo": "110-caja",
            "transferencia": "112-banco", "Transferencia": "112-banco",
            "cheque": "112-banco", "Cheque": "112-banco",
        }
        return _MAP.get(payment_method, "110-caja")
