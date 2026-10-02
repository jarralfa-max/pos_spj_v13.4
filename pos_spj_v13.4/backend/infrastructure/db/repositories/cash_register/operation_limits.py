"""Tope vigente de una operación de Caja (`cash_operation_limits`).

Vive en la capa de repositorios para que cualquier contexto (Caja, Ventas al
reembolsar una devolución) lo lea sin depender de la composición de la
pantalla de Caja. Sin fila vigente el tope es 0: Caja rechaza la operación
(falla cerrado).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.cash_register.policies.security_policies import CashMonetaryLimitPolicy


def cash_limit_policy(connection, operation_type: str) -> CashMonetaryLimitPolicy:
    occurred_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    row = connection.execute(
        """SELECT approval_threshold,hard_cap
        FROM cash_operation_limits
        WHERE operation_type=? AND effective_from<=?
          AND (effective_to IS NULL OR effective_to>?)
        ORDER BY effective_from DESC LIMIT 1""",
        (operation_type, occurred_at, occurred_at),
    ).fetchone()
    threshold = Decimal(str(row[0])) if row else Decimal("0")
    hard_cap = Decimal(str(row[1])) if row else Decimal("0")
    return CashMonetaryLimitPolicy(approval_threshold=threshold, hard_cap=hard_cap)
