"""FinanceCommandService — la ÚNICA puerta de la UI a los comandos financieros.

Auditoría d9f2bca F02: la entrada al módulo exigía ``FINANZAS.ver`` y ningún
comando exigía nada más; una sesión de sólo lectura registraba una
transferencia y, sin sesión, se registraba una aportación con
``created_by`` NULL. Aquí cada comando:

1. resuelve el actor de la sesión viva — sin actor, rechaza (falla cerrada);
2. exige su permiso ``FINANZAS.<accion>`` por la política;
3. llama al caso de uso propagando el actor al asiento y a la auditoría.

Un rechazo ocurre ANTES de abrir cualquier unidad de trabajo: no cambia ningún
registro. Los casos de uso siguen siendo los bloques internos que también usan
los handlers de integración (Ventas, Compras, Caja), que no son comandos de un
usuario sino hechos ya autorizados en su módulo de origen.
"""

from __future__ import annotations

import functools
import logging
from datetime import date
from typing import Callable

from backend.application.finance.authorization import FinanceAuthorizationPolicy
from backend.application.finance.permissions import FinancePermissions as P
from backend.domain.finance.exceptions import FinancePermissionDeniedError
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.finance.commands")


def _dispatches(method):
    """Tras un comando exitoso, entrega el ``finance_outbox`` (F21)."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        result = method(self, *args, **kwargs)
        self._after()
        return result
    return wrapper


class FinanceCommandService:
    def __init__(self, *, connection_provider: Callable, use_cases: dict,
                 authorization: FinanceAuthorizationPolicy,
                 actor_provider: Callable[[], str | None],
                 after_command: Callable[[], object] | None = None) -> None:
        """``after_command``: se llama tras cada comando exitoso (la
        composición entrega ahí el ``finance_outbox``); nunca propaga."""
        self._conn = connection_provider
        self._uc = use_cases
        self._auth = authorization
        self._actor_provider = actor_provider
        self._after_command = after_command

    def _after(self) -> None:
        if self._after_command is None:
            return
        try:
            self._after_command()
        except Exception:  # la entrega queda pendiente y se reintenta
            logger.exception("despacho de finance_outbox fallido")

    # ── helpers ───────────────────────────────────────────────────────────
    def _actor(self, permission: str) -> str:
        actor = str(self._actor_provider() or "").strip()
        if not actor:
            raise FinancePermissionDeniedError("Operación sin usuario autenticado")
        self._auth.require(actor, permission)
        return actor

    def can(self, permission: str) -> bool:
        actor = str(self._actor_provider() or "").strip()
        return self._auth.has_permission(actor, permission)

    # ── cobranza ──────────────────────────────────────────────────────────
    @_dispatches
    def register_collection(self, *, receivable_id: str, amount: str,
                            treasury_account_id: str, reference: str = "",
                            collection_date: date | None = None) -> str:
        actor = self._actor(P.COLLECTION_REGISTER)
        return self._uc["register_collection"].execute(
            self._conn(), receivable_id=receivable_id, amount=amount,
            treasury_account_id=treasury_account_id,
            collection_date=collection_date or date.today(), reference=reference,
            operation_id=new_uuid(), created_by=actor)

    # ── pagos a proveedor ────────────────────────────────────────────────
    @_dispatches
    def schedule_payment(self, *, payable_id: str, amount: str, treasury_account_id: str,
                         scheduled_date: date, reference: str = ""):
        actor = self._actor(P.PAYMENT_SCHEDULE)
        return self._uc["schedule_payment"].execute(
            self._conn(), payable_id=payable_id, amount=amount, scheduled_date=scheduled_date,
            treasury_account_id=treasury_account_id, scheduled_by=actor,
            reference=reference, operation_id=new_uuid())

    @_dispatches
    def authorize_payment(self, payment_id: str):
        actor = self._actor(P.PAYMENT_AUTHORIZE)
        return self._uc["authorize_payment"].execute(
            self._conn(), payment_id=payment_id, authorized_by=actor, operation_id=new_uuid())

    @_dispatches
    def execute_payment(self, payment_id: str, *, execution_reference: str,
                        executed_date: date | None = None):
        actor = self._actor(P.PAYMENT_EXECUTE)
        return self._uc["execute_payment"].execute(
            self._conn(), payment_id=payment_id, executed_date=executed_date or date.today(),
            operation_id=new_uuid(), executed_by=actor,
            execution_reference=execution_reference)

    # ── tesorería / capital ──────────────────────────────────────────────
    @_dispatches
    def treasury_transfer(self, *, source_id: str, target_id: str, amount: str,
                          reference: str = "") -> str:
        actor = self._actor(P.TREASURY_TRANSFER)
        return self._uc["treasury_transfer"].execute(
            self._conn(), source_treasury_account_id=source_id,
            target_treasury_account_id=target_id, amount=amount,
            transfer_date=date.today(), reference=reference, operation_id=new_uuid(),
            created_by=actor)

    @_dispatches
    def capital_contribution(self, *, amount: str, treasury_account_id: str,
                             contributor: str = "") -> str:
        actor = self._actor(P.CAPITAL_REGISTER)
        return self._uc["capital_contribution"].execute(
            self._conn(), amount=amount, contribution_date=date.today(),
            treasury_account_id=treasury_account_id, contributor=contributor,
            operation_id=new_uuid(), created_by=actor)

    # ── conciliación ─────────────────────────────────────────────────────
    @_dispatches
    def import_statement(self, *, treasury_account_id: str, statement_date: date,
                         opening_balance: str, closing_balance: str, lines: list[dict]):
        self._actor(P.RECONCILIATION_OPERATE)
        return self._uc["import_statement"].execute(
            self._conn(), treasury_account_id=treasury_account_id,
            statement_date=statement_date, opening_balance=opening_balance,
            closing_balance=closing_balance, lines=lines, operation_id=new_uuid())

    @_dispatches
    def start_reconciliation(self, bank_statement_id: str):
        self._actor(P.RECONCILIATION_OPERATE)
        return self._uc["reconcile"].start(self._conn(), bank_statement_id=bank_statement_id,
                                           operation_id=new_uuid())

    def reconciliation_candidates(self, reconciliation_id: str) -> dict:
        self._actor(P.RECONCILIATION_OPERATE)
        return self._uc["reconcile"].candidates(self._conn(),
                                                reconciliation_id=reconciliation_id)

    @_dispatches
    def match(self, *, reconciliation_id: str, bank_statement_line_id: str,
              journal_line_id: str) -> None:
        actor = self._actor(P.RECONCILIATION_OPERATE)
        self._uc["reconcile"].match(
            self._conn(), reconciliation_id=reconciliation_id,
            bank_statement_line_id=bank_statement_line_id, journal_line_id=journal_line_id,
            matched_by=actor)

    @_dispatches
    def complete_reconciliation(self, reconciliation_id: str, *,
                                difference_reason: str | None = None) -> None:
        actor = self._actor(P.RECONCILIATION_OPERATE)
        if (difference_reason or "").strip():
            self._auth.require(actor, P.RECONCILIATION_ACCEPT_DIFFERENCE)
        self._uc["reconcile"].complete(self._conn(), reconciliation_id=reconciliation_id,
                                       completed_by=actor,
                                       difference_reason=difference_reason)

    @_dispatches
    def revert_reconciliation(self, reconciliation_id: str, *, reason: str) -> None:
        actor = self._actor(P.RECONCILIATION_REVERT)
        self._uc["reconcile"].revert(self._conn(), reconciliation_id=reconciliation_id,
                                     reverted_by=actor, reason=reason)

    # ── presupuesto / gasto ──────────────────────────────────────────────
    @_dispatches
    def expense_request(self, *, account_id: str, amount: str) -> str:
        actor = self._actor(P.EXPENSE_REQUEST)
        return self._uc["expense_request"].execute(
            self._conn(), account_id=account_id, amount=amount, request_date=date.today(),
            operation_id=new_uuid(), requested_by=actor)

    @_dispatches
    def accrue_expense(self, expense_request_id: str, *, document_reference: str) -> None:
        actor = self._actor(P.EXPENSE_RESOLVE)
        self._uc["resolve_expense"].accrue(
            self._conn(), expense_request_id=expense_request_id,
            document_reference=document_reference, resolved_by=actor)

    @_dispatches
    def release_expense(self, expense_request_id: str, *, reason: str) -> None:
        actor = self._actor(P.EXPENSE_RESOLVE)
        self._uc["resolve_expense"].release(
            self._conn(), expense_request_id=expense_request_id, reason=reason,
            resolved_by=actor)

    # ── activos ──────────────────────────────────────────────────────────
    @_dispatches
    def run_depreciation(self, year: int, month: int) -> list[str]:
        actor = self._actor(P.ASSET_DEPRECIATE)
        return self._uc["run_depreciation"].execute(
            self._conn(), year=year, month=month, operation_id=new_uuid(), created_by=actor)

    # ── periodos / asientos ──────────────────────────────────────────────
    @_dispatches
    def close_period(self, year: int, month: int, *, soft: bool):
        actor = self._actor(P.PERIOD_CLOSE)
        return self._uc["close_period"].execute(
            self._conn(), year, month, closed_by=actor, operation_id=new_uuid(), soft=soft)

    @_dispatches
    def reopen_period(self, year: int, month: int, *, reason: str):
        actor = self._actor(P.PERIOD_REOPEN)
        return self._uc["reopen_period"].execute(
            self._conn(), year, month, reason=reason, operation_id=new_uuid(),
            reopened_by=actor)

    @_dispatches
    def authorize_close_exception(self, exception_id: str, *, reason: str) -> None:
        actor = self._actor(P.CLOSE_EXCEPTION_AUTHORIZE)
        self._uc["authorize_close_exception"].execute(
            self._conn(), exception_id=exception_id, authorized_by=actor, reason=reason)

    @_dispatches
    def reverse_entry(self, journal_entry_id: str, *, reason: str):
        actor = self._actor(P.ENTRY_REVERSE)
        return self._uc["reverse_entry"].execute(
            self._conn(), journal_entry_id=journal_entry_id, reason=reason,
            reversal_date=date.today(), operation_id=new_uuid(), reversed_by=actor)
