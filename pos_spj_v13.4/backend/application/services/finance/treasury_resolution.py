"""Qué cuenta de tesorería corresponde a un tipo y una sucursal.

Una sola definición para Compras, Ventas y devoluciones (SDLC-PAY-004): la de
sucursal gana; sin ella, la global. La cuenta del procesador se resuelve aquí y
no por un perfil contable: entradas y salidas tienen que caer en el mismo espejo
para poder conciliarse contra la operación.

Decisión del responsable (2026-11-05): una sola cuenta de procesadores, y la
venta carga directo a ella (no a la 1120 hasta la liquidación).
"""

from __future__ import annotations

from backend.domain.finance.entities.treasury_account import TreasuryAccount
from backend.domain.finance.enums import TreasuryAccountType
from backend.domain.finance.exceptions import FinanceDomainError


def treasury_candidates(accounts, account_type: TreasuryAccountType,
                        branch_id: str | None) -> list[TreasuryAccount]:
    candidates = [a for a in accounts if a.account_type == account_type]
    if branch_id:
        branch_scoped = [a for a in candidates if a.branch_id == branch_id]
        return branch_scoped or [a for a in candidates if a.branch_id is None]
    return candidates


def processor_ledger_account_id(uow, *, branch_id: str | None) -> str:
    """El espejo del mayor de LA cuenta de procesadores. Sin exactamente una no se
    adivina: el evento queda pendiente a la vista, en vez de caer en la puente."""
    candidates = treasury_candidates(
        uow.treasury.list_active(), TreasuryAccountType.PAYMENT_PROCESSOR, branch_id)
    if len(candidates) != 1:
        raise FinanceDomainError(
            f"Hay {len(candidates)} cuentas de tesorería activas de procesador para esta "
            "sucursal; se necesita exactamente una")
    return candidates[0].ledger_account_id
