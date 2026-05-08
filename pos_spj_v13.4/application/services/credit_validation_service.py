# application/services/credit_validation_service.py — SPJ POS v13.4
"""
CreditValidationService — rich credit pre-authorization for checkout.

Checks beyond the basic limit/balance comparison:
- Customer exists and is active
- Credit is enabled (credit_limit > 0)
- Sufficient available credit
- No overdue unpaid invoices (optional enforcement)
- Customer not explicitly blocked

Designed to be called AFTER the payment dialog confirms the user chose
"Crédito", so the financed_balance is the actual credit portion.
"""
from __future__ import annotations

import logging
from typing import Tuple

logger = logging.getLogger("spj.credit_validation")


class CreditValidationService:
    """
    Stateless service: every public method receives what it needs and returns
    (ok: bool, reason: str).  No side-effects, no DB mutations.
    """

    def __init__(self, db_conn, block_on_overdue: bool = False):
        self.db = db_conn
        self._block_on_overdue = block_on_overdue

    # ── Public API ────────────────────────────────────────────────────────────

    def validate(self, cliente_id: int, financed_amount: float) -> Tuple[bool, str]:
        """
        Full pre-authorization check for a credit sale.

        Args:
            cliente_id:      Customer PK.
            financed_amount: The portion being put on credit (>0).

        Returns:
            (True, "")           — approved
            (False, "reason...")  — rejected
        """
        if financed_amount <= 0:
            return False, "El monto financiado debe ser mayor a cero."

        customer = self._get_customer(cliente_id)
        if customer is None:
            return False, f"Cliente ID {cliente_id} no encontrado o inactivo."

        if customer["credit_limit"] <= 0:
            return (
                False,
                f"El cliente '{customer['nombre']}' no tiene línea de crédito habilitada.",
            )

        disponible = customer["credit_limit"] - customer["credit_balance"]
        if disponible < financed_amount:
            return (
                False,
                f"Crédito insuficiente para '{customer['nombre']}': "
                f"disponible ${disponible:,.2f}, requerido ${financed_amount:,.2f}.",
            )

        if self._block_on_overdue:
            overdue = self._has_overdue(cliente_id)
            if overdue:
                return (
                    False,
                    f"El cliente '{customer['nombre']}' tiene facturas vencidas pendientes. "
                    "Regularice el adeudo antes de otorgar nuevo crédito.",
                )

        return True, ""

    def available_credit(self, cliente_id: int) -> float:
        """Returns the available credit for a customer, or 0.0 if not found."""
        customer = self._get_customer(cliente_id)
        if not customer:
            return 0.0
        return max(0.0, customer["credit_limit"] - customer["credit_balance"])

    # ── Private helpers ───────────────────────────────────────────────────────

    def _get_customer(self, cliente_id: int) -> dict | None:
        try:
            row = self.db.execute(
                "SELECT id, nombre, activo, "
                "COALESCE(credit_limit, 0.0)   AS credit_limit, "
                "COALESCE(credit_balance, 0.0) AS credit_balance "
                "FROM clientes WHERE id = ? AND activo = 1",
                (cliente_id,),
            ).fetchone()
        except Exception as exc:
            logger.warning("CreditValidationService._get_customer: %s", exc)
            return None

        if not row:
            return None

        return {
            "id":             row[0],
            "nombre":         row[1],
            "activo":         bool(row[2]),
            "credit_limit":   float(row[3]),
            "credit_balance": float(row[4]),
        }

    def _has_overdue(self, cliente_id: int) -> bool:
        """Returns True if the customer has any overdue CxC with saldo_pendiente > 0."""
        try:
            row = self.db.execute(
                "SELECT COUNT(*) FROM cuentas_por_cobrar "
                "WHERE cliente_id = ? AND estado = 'vencida' AND saldo_pendiente > 0",
                (cliente_id,),
            ).fetchone()
            return bool(row and row[0] > 0)
        except Exception:
            return False
