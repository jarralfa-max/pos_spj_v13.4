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


class EffectiveCashLimitPolicy:
    """El tope VIGENTE al momento de cada operación, no el del día que se abrió Caja.

    Los casos de uso se construyen una vez al abrir la pantalla; antes recibían el
    tope ya leído, así que un límite capturado en Caja → Configuración no aplicaba
    hasta reabrir el módulo (medido el 2026-10-07). Misma interfaz que
    `CashMonetaryLimitPolicy`, resuelta en cada consulta.
    """

    def __init__(self, connection, operation_type: str) -> None:
        self._connection = connection
        self.operation_type = operation_type

    def _current(self) -> CashMonetaryLimitPolicy:
        return cash_limit_policy(self._connection, self.operation_type)

    @property
    def approval_threshold(self) -> Decimal:
        return self._current().approval_threshold

    @property
    def hard_cap(self) -> Decimal:
        return self._current().hard_cap

    def evaluate(self, amount: Decimal):
        return self._current().evaluate(amount)

    def require_operable(self, amount: Decimal):
        return self._current().require_operable(amount)
