"""FinanceCommandService — la ÚNICA puerta de la UI a los comandos financieros.

Cada comando:

1. resuelve el actor de la sesión viva — sin actor, rechaza (falla cerrada);
2. exige su permiso ``FINANZAS.<accion>`` por la política (§28);
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
from backend.domain.finance.enums import (
    AccountType,
    AuditAction,
    CapitalMovementKind,
    CashFlowCategory,
    FixedAssetStatus,
    JournalType,
    TaxDirection,
    TaxKind,
    TreasuryAccountType,
    TreasuryMovementKind,
)
from backend.domain.finance.exceptions import PermissionDeniedError
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
                 after_command: Callable[[], object] | None = None,
                 today: Callable[[], date] = date.today) -> None:
        """``after_command``: se llama tras cada comando exitoso (la composición
        entrega ahí el ``finance_outbox``); un fallo de entrega se registra y
        el evento queda pendiente para reintento."""
        self._conn = connection_provider
        self._uc = use_cases
        self._auth = authorization
        self._actor_provider = actor_provider
        self._after_command = after_command
        self._today = today

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
            raise PermissionDeniedError("Operación sin usuario autenticado")
        self._auth.require(actor, permission)
        return actor

    def can(self, permission: str) -> bool:
        actor = str(self._actor_provider() or "").strip()
        return self._auth.has_permission(actor, permission)

    # ── plan de cuentas ───────────────────────────────────────────────────
    @_dispatches
    def create_account(self, *, code: str, name: str, account_type: AccountType,
                       parent_account_id: str | None, posting_allowed: bool,
                       cash_flow_category: CashFlowCategory,
                       reconciliation_required: bool = False):
        actor = self._actor(P.ACCOUNT_MANAGE)
        return self._uc["create_account"].execute(
            self._conn(), code=code, name=name, account_type=account_type,
            parent_account_id=parent_account_id, posting_allowed=posting_allowed,
            cash_flow_category=cash_flow_category,
            reconciliation_required=reconciliation_required, operation_id=new_uuid(),
            created_by=actor)

    @_dispatches
    def update_account(self, account_id: str, **changes):
        actor = self._actor(P.ACCOUNT_MANAGE)
        return self._uc["update_account"].execute(
            self._conn(), account_id=account_id, operation_id=new_uuid(), updated_by=actor,
            **changes)

    # ── asientos manuales ─────────────────────────────────────────────────
    @_dispatches
    def create_journal_entry(self, *, entry_date: date, description: str, lines: list[dict],
                             journal_type: JournalType = JournalType.GENERAL,
                             currency_code: str = "MXN", exchange_rate: str | None = None,
                             branch_id: str | None = None):
        actor = self._actor(P.JOURNAL_CREATE)
        return self._uc["create_journal_entry"].execute(
            self._conn(), entry_date=entry_date, description=description, lines=lines,
            journal_type=journal_type, currency_code=currency_code,
            exchange_rate=exchange_rate, branch_id=branch_id, operation_id=new_uuid(),
            created_by=actor)

    @_dispatches
    def update_journal_entry(self, journal_entry_id: str, **changes):
        actor = self._actor(P.JOURNAL_CREATE)
        return self._uc["update_journal_entry"].execute(
            self._conn(), journal_entry_id=journal_entry_id, operation_id=new_uuid(),
            updated_by=actor, **changes)

    @_dispatches
    def cancel_journal_entry(self, journal_entry_id: str, *, reason: str):
        actor = self._actor(P.JOURNAL_CREATE)
        return self._uc["cancel_journal_entry"].execute(
            self._conn(), journal_entry_id=journal_entry_id, reason=reason,
            operation_id=new_uuid(), cancelled_by=actor)

    @_dispatches
    def validate_journal_entry(self, journal_entry_id: str):
        actor = self._actor(P.JOURNAL_VALIDATE)
        return self._uc["validate_journal_entry"].execute(
            self._conn(), journal_entry_id=journal_entry_id, operation_id=new_uuid(),
            validated_by=actor)

    @_dispatches
    def post_journal_entry(self, journal_entry_id: str):
        actor = self._actor(P.JOURNAL_POST)
        # Ajuste en periodo pre-cerrado: sólo con su permiso especial (§9).
        allow_soft_closed = self._auth.has_permission(actor, P.ADJUSTMENT_CLOSED_PERIOD)
        return self._uc["post_journal_entry"].execute(
            self._conn(), journal_entry_id=journal_entry_id, operation_id=new_uuid(),
            posted_by=actor, allow_soft_closed=allow_soft_closed)

    @_dispatches
    def reverse_entry(self, journal_entry_id: str, *, reason: str):
        actor = self._actor(P.ENTRY_REVERSE)
        return self._uc["reverse_entry"].execute(
            self._conn(), journal_entry_id=journal_entry_id, reason=reason,
            reversal_date=self._today(), operation_id=new_uuid(), reversed_by=actor)

    # ── periodos ──────────────────────────────────────────────────────────
    @_dispatches
    def close_period(self, year: int, month: int, *, soft: bool):
        actor = self._actor(P.PERIOD_CLOSE)
        return self._uc["close_period"].execute(
            self._conn(), year, month, closed_by=actor, operation_id=new_uuid(), soft=soft)

    def close_checklist(self, year: int, month: int):
        self._actor(P.PERIOD_READ)
        return self._uc["close_period"].checklist(self._conn(), year, month)

    @_dispatches
    def reopen_period(self, year: int, month: int, *, reason: str):
        actor = self._actor(P.PERIOD_REOPEN)
        return self._uc["reopen_period"].execute(
            self._conn(), year, month, reason=reason, operation_id=new_uuid(),
            reopened_by=actor)

    @_dispatches
    def open_period(self, year: int, month: int):
        actor = self._actor(P.PERIOD_CLOSE)
        return self._uc["open_period"].execute(self._conn(), year, month,
                                               operation_id=new_uuid(), opened_by=actor)

    @_dispatches
    def authorize_close_exception(self, exception_id: str, *, reason: str) -> None:
        actor = self._actor(P.CLOSE_EXCEPTION_AUTHORIZE)
        self._uc["authorize_close_exception"].execute(
            self._conn(), exception_id=exception_id, authorized_by=actor, reason=reason,
            operation_id=new_uuid())

    # ── cobranza ──────────────────────────────────────────────────────────
    @_dispatches
    def create_receivable(self, *, customer_id: str, amount: str, document_number: str,
                          issue_date: date, counterpart_account_id: str,
                          due_date: date | None = None, credit_term_days: int | None = None,
                          branch_id: str | None = None):
        actor = self._actor(P.RECEIVABLE_MANAGE)
        return self._uc["create_receivable"].execute(
            self._conn(), customer_id=customer_id, amount=amount,
            document_number=document_number, issue_date=issue_date, due_date=due_date,
            credit_term_days=credit_term_days, branch_id=branch_id,
            counterpart_account_id=counterpart_account_id, operation_id=new_uuid(),
            created_by=actor)

    @_dispatches
    def register_collection(self, *, customer_id: str, amount: str, treasury_account_id: str,
                            applications: list[dict] | None = None, reference: str = "",
                            payment_method: str = "BANK_TRANSFER",
                            collection_date: date | None = None):
        actor = self._actor(P.COLLECTION_REGISTER)
        if applications:
            self._auth.require(actor, P.COLLECTION_APPLY)
        return self._uc["register_collection"].execute(
            self._conn(), customer_id=customer_id, amount=amount,
            treasury_account_id=treasury_account_id, applications=applications,
            collection_date=collection_date or self._today(), reference=reference,
            payment_method=payment_method, operation_id=new_uuid(), created_by=actor)

    @_dispatches
    def apply_collection(self, *, collection_id: str, applications: list[dict]):
        actor = self._actor(P.COLLECTION_APPLY)
        return self._uc["apply_collection"].execute(
            self._conn(), collection_id=collection_id, applications=applications,
            application_date=self._today(), operation_id=new_uuid(), applied_by=actor)

    @_dispatches
    def write_off_receivable(self, receivable_id: str, *, reason: str):
        actor = self._actor(P.WRITE_OFF_AUTHORIZE)
        return self._uc["write_off_receivable"].execute(
            self._conn(), receivable_id=receivable_id, reason=reason,
            write_off_date=self._today(), operation_id=new_uuid(), authorized_by=actor)

    @_dispatches
    def dispute_receivable(self, receivable_id: str, *, reason: str) -> None:
        actor = self._actor(P.CREDIT_MANAGE)
        self._uc["receivable_followup"].open(
            self._conn(), receivable_id=receivable_id, reason=reason,
            operation_id=new_uuid(), disputed_by=actor)

    @_dispatches
    def resolve_receivable_dispute(self, receivable_id: str, *, resolution: str) -> None:
        actor = self._actor(P.CREDIT_MANAGE)
        self._uc["receivable_followup"].resolve(
            self._conn(), receivable_id=receivable_id, resolution=resolution,
            as_of=self._today(), operation_id=new_uuid(), resolved_by=actor)

    @_dispatches
    def register_payment_promise(self, receivable_id: str, *, promised_date: date,
                                 promised_amount: str, note: str = "") -> str:
        actor = self._actor(P.CREDIT_MANAGE)
        return self._uc["payment_promise"].execute(
            self._conn(), receivable_id=receivable_id, promised_date=promised_date,
            promised_amount=promised_amount, note=note, operation_id=new_uuid(),
            created_by=actor)

    @_dispatches
    def mark_overdue_documents(self):
        self._actor(P.RECEIVABLE_MANAGE)
        return self._uc["mark_overdue"].execute(self._conn(), as_of=self._today())

    # ── cuentas por pagar ─────────────────────────────────────────────────
    @_dispatches
    def create_payable(self, *, supplier_id: str, amount: str, document_number: str,
                       issue_date: date, debit_nature, counterpart_account_id: str | None = None,
                       due_date: date | None = None, retention_amount: str | None = None,
                       priority=None, payment_terms: str = "",
                       early_payment_discount_percent: str | None = None,
                       early_payment_discount_until: date | None = None,
                       branch_id: str | None = None):
        actor = self._actor(P.PAYABLE_MANAGE)
        kwargs = {} if priority is None else {"priority": priority}
        return self._uc["create_payable"].execute(
            self._conn(), supplier_id=supplier_id, amount=amount,
            document_number=document_number, issue_date=issue_date, due_date=due_date,
            branch_id=branch_id, debit_nature=debit_nature,
            counterpart_account_id=counterpart_account_id, retention_amount=retention_amount,
            payment_terms=payment_terms,
            early_payment_discount_percent=early_payment_discount_percent,
            early_payment_discount_until=early_payment_discount_until,
            operation_id=new_uuid(), created_by=actor, **kwargs)

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
            self._conn(), payment_id=payment_id, executed_date=executed_date or self._today(),
            operation_id=new_uuid(), executed_by=actor,
            execution_reference=execution_reference)

    @_dispatches
    def cancel_payment(self, payment_id: str, *, reason: str) -> None:
        actor = self._actor(P.PAYMENT_SCHEDULE)
        self._uc["payable_controls"].cancel_payment(
            self._conn(), payment_id=payment_id, reason=reason, operation_id=new_uuid(),
            actor=actor, as_of=self._today())

    @_dispatches
    def block_payable(self, payable_id: str, *, reason: str) -> None:
        actor = self._actor(P.PAYABLE_MANAGE)
        self._uc["payable_controls"].block(self._conn(), payable_id=payable_id, reason=reason,
                                           operation_id=new_uuid(), actor=actor)

    @_dispatches
    def unblock_payable(self, payable_id: str, *, reason: str) -> None:
        actor = self._actor(P.PAYABLE_UNBLOCK)
        self._uc["payable_controls"].unblock(self._conn(), payable_id=payable_id,
                                             reason=reason, operation_id=new_uuid(),
                                             actor=actor)

    @_dispatches
    def dispute_payable(self, payable_id: str, *, reason: str) -> None:
        actor = self._actor(P.PAYABLE_MANAGE)
        self._uc["payable_controls"].dispute(self._conn(), payable_id=payable_id,
                                             reason=reason, operation_id=new_uuid(),
                                             actor=actor)

    @_dispatches
    def resolve_payable_dispute(self, payable_id: str, *, resolution: str) -> None:
        actor = self._actor(P.PAYABLE_MANAGE)
        self._uc["payable_controls"].resolve_dispute(
            self._conn(), payable_id=payable_id, resolution=resolution, as_of=self._today(),
            operation_id=new_uuid(), actor=actor)

    @_dispatches
    def register_supplier_advance(self, *, supplier_id: str, amount: str,
                                  treasury_account_id: str, execution_reference: str):
        actor = self._actor(P.PAYMENT_EXECUTE)
        return self._uc["supplier_advance"].execute(
            self._conn(), supplier_id=supplier_id, amount=amount,
            treasury_account_id=treasury_account_id, advance_date=self._today(),
            execution_reference=execution_reference, operation_id=new_uuid(),
            created_by=actor)

    @_dispatches
    def apply_supplier_advance(self, *, supplier_advance_id: str, payable_id: str,
                               amount: str) -> str:
        actor = self._actor(P.PAYABLE_MANAGE)
        return self._uc["apply_supplier_advance"].execute(
            self._conn(), supplier_advance_id=supplier_advance_id, payable_id=payable_id,
            amount=amount, application_date=self._today(), operation_id=new_uuid(),
            applied_by=actor)

    # ── tesorería / capital ──────────────────────────────────────────────
    @_dispatches
    def treasury_transfer(self, *, source_id: str, target_id: str, amount: str,
                          reference: str = "") -> str:
        actor = self._actor(P.TREASURY_TRANSFER)
        return self._uc["treasury_transfer"].execute(
            self._conn(), source_treasury_account_id=source_id,
            target_treasury_account_id=target_id, amount=amount,
            transfer_date=self._today(), reference=reference, operation_id=new_uuid(),
            created_by=actor)

    @_dispatches
    def treasury_movement(self, *, treasury_account_id: str, kind: TreasuryMovementKind,
                          amount: str, counterpart_account_id: str | None = None,
                          reference: str = "", description: str = "") -> str:
        actor = self._actor(P.TREASURY_MOVEMENT)
        return self._uc["treasury_movement"].execute(
            self._conn(), treasury_account_id=treasury_account_id, kind=kind, amount=amount,
            movement_date=self._today(), counterpart_account_id=counterpart_account_id,
            reference=reference, description=description, operation_id=new_uuid(),
            created_by=actor)

    @_dispatches
    def create_treasury_account(self, *, name: str, account_type: TreasuryAccountType,
                                ledger_account_id: str, bank_name: str | None = None,
                                account_number: str | None = None, restricted: bool = False,
                                allows_overdraft: bool = False, branch_id: str | None = None):
        actor = self._actor(P.TREASURY_MANAGE)
        return self._uc["treasury_account"].create(
            self._conn(), name=name, account_type=account_type,
            ledger_account_id=ledger_account_id, bank_name=bank_name,
            account_number=account_number, restricted=restricted,
            allows_overdraft=allows_overdraft, branch_id=branch_id, operation_id=new_uuid(),
            created_by=actor)

    @_dispatches
    def update_treasury_account(self, treasury_account_id: str, **changes):
        actor = self._actor(P.TREASURY_MANAGE)
        return self._uc["treasury_account"].update(
            self._conn(), treasury_account_id=treasury_account_id, operation_id=new_uuid(),
            updated_by=actor, **changes)

    @_dispatches
    def capital_movement(self, *, kind: CapitalMovementKind, amount: str,
                         treasury_account_id: str, counterparty: str = "",
                         interest_amount: str | None = None, loan_id: str | None = None,
                         maturity_date: date | None = None) -> str:
        actor = self._actor(P.CAPITAL_REGISTER)
        return self._uc["capital_movement"].execute(
            self._conn(), kind=kind, amount=amount, movement_date=self._today(),
            treasury_account_id=treasury_account_id, counterparty=counterparty,
            interest_amount=interest_amount, loan_id=loan_id, maturity_date=maturity_date,
            operation_id=new_uuid(), created_by=actor)

    def capital_contribution(self, *, amount: str, treasury_account_id: str,
                             contributor: str = "") -> str:
        return self.capital_movement(kind=CapitalMovementKind.CONTRIBUTION, amount=amount,
                                     treasury_account_id=treasury_account_id,
                                     counterparty=contributor)

    # ── conciliación ─────────────────────────────────────────────────────
    @_dispatches
    def import_statement(self, *, treasury_account_id: str, statement_date: date,
                         opening_balance: str, closing_balance: str, lines: list[dict],
                         source_format: str = "MANUAL", file_name: str = ""):
        actor = self._actor(P.STATEMENT_IMPORT)
        return self._uc["import_statement"].execute(
            self._conn(), treasury_account_id=treasury_account_id,
            statement_date=statement_date, opening_balance=opening_balance,
            closing_balance=closing_balance, lines=lines, operation_id=new_uuid(),
            imported_by=actor, source_format=source_format, file_name=file_name)

    @_dispatches
    def start_reconciliation(self, bank_statement_id: str):
        actor = self._actor(P.RECONCILIATION_OPERATE)
        return self._uc["reconcile"].start(self._conn(), bank_statement_id=bank_statement_id,
                                           operation_id=new_uuid(), started_by=actor)

    def suggest_matches(self, reconciliation_id: str) -> int:
        self._actor(P.RECONCILIATION_OPERATE)
        return self._uc["reconcile"].suggest(self._conn(), reconciliation_id=reconciliation_id)

    def reconciliation_candidates(self, reconciliation_id: str) -> dict:
        self._actor(P.RECONCILIATION_OPERATE)
        return self._uc["reconcile"].candidates(self._conn(),
                                                reconciliation_id=reconciliation_id)

    @_dispatches
    def match(self, *, reconciliation_id: str, bank_statement_line_id: str,
              journal_line_id: str) -> bool:
        actor = self._actor(P.RECONCILIATION_OPERATE)
        return self._uc["reconcile"].match(
            self._conn(), reconciliation_id=reconciliation_id,
            bank_statement_line_id=bank_statement_line_id, journal_line_id=journal_line_id,
            matched_by=actor)

    @_dispatches
    def ignore_statement_line(self, *, reconciliation_id: str, bank_statement_line_id: str,
                              reason: str) -> None:
        actor = self._actor(P.RECONCILIATION_OPERATE)
        self._uc["reconcile"].ignore(self._conn(), reconciliation_id=reconciliation_id,
                                     bank_statement_line_id=bank_statement_line_id,
                                     reason=reason, ignored_by=actor)

    @_dispatches
    def reconciliation_adjustment(self, *, reconciliation_id: str, bank_statement_line_id: str,
                                  kind: TreasuryMovementKind | None = None,
                                  counterpart_account_id: str | None = None,
                                  reason: str = "") -> str:
        actor = self._actor(P.RECONCILIATION_ADJUST)
        return self._uc["reconciliation_adjustment"].execute(
            self._conn(), reconciliation_id=reconciliation_id,
            bank_statement_line_id=bank_statement_line_id, kind=kind,
            counterpart_account_id=counterpart_account_id, reason=reason,
            operation_id=new_uuid(), adjusted_by=actor)

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
    def create_budget(self, *, name: str, fiscal_year: int, lines: list[dict],
                      blocking: bool = True, branch_id: str | None = None):
        actor = self._actor(P.BUDGET_CREATE)
        return self._uc["create_budget"].execute(
            self._conn(), name=name, fiscal_year=fiscal_year, lines=lines, blocking=blocking,
            branch_id=branch_id, operation_id=new_uuid(), created_by=actor)

    @_dispatches
    def create_budget_version(self, budget_id: str):
        actor = self._actor(P.BUDGET_CREATE)
        return self._uc["create_budget_version"].execute(
            self._conn(), budget_id=budget_id, operation_id=new_uuid(), created_by=actor)

    @_dispatches
    def budget_action(self, budget_id: str, action: str, *, reason: str = ""):
        permission = P.BUDGET_CREATE if action == "submit" else P.BUDGET_APPROVE
        actor = self._actor(permission)
        workflow = self._uc["budget_workflow"]
        op = new_uuid()
        if action == "submit":
            return workflow.submit(self._conn(), budget_id=budget_id, submitted_by=actor,
                                   operation_id=op)
        if action == "approve":
            return workflow.approve(self._conn(), budget_id=budget_id, approved_by=actor,
                                    operation_id=op)
        if action == "reject":
            return workflow.reject(self._conn(), budget_id=budget_id, rejected_by=actor,
                                   reason=reason, operation_id=op)
        if action == "activate":
            return workflow.activate(self._conn(), budget_id=budget_id, actor=actor,
                                     operation_id=op)
        if action == "close":
            return workflow.close(self._conn(), budget_id=budget_id, actor=actor,
                                  operation_id=op)
        if action == "cancel":
            return workflow.cancel(self._conn(), budget_id=budget_id, actor=actor,
                                   reason=reason, operation_id=op)
        raise ValueError(f"Acción de presupuesto desconocida: {action}")

    @_dispatches
    def expense_request(self, *, account_id: str, amount: str, category: str = "",
                        description: str = "", cost_center_id: str | None = None,
                        project_id: str | None = None, department_id: str | None = None,
                        branch_id: str | None = None, supplier_id: str | None = None) -> str:
        actor = self._actor(P.EXPENSE_REQUEST)
        return self._uc["expense_request"].execute(
            self._conn(), account_id=account_id, amount=amount, request_date=self._today(),
            category=category, description=description, cost_center_id=cost_center_id,
            project_id=project_id, department_id=department_id, branch_id=branch_id,
            supplier_id=supplier_id, operation_id=new_uuid(), requested_by=actor)

    @_dispatches
    def approve_expense(self, expense_request_id: str, *, reason: str = "",
                        authorize_excess: bool = False) -> bool:
        actor = self._actor(P.EXPENSE_APPROVE)
        if authorize_excess:
            self._auth.require(actor, P.BUDGET_AUTHORIZE_EXCESS)
        return self._uc["approve_expense"].approve(
            self._conn(), expense_request_id=expense_request_id, approver_id=actor,
            reason=reason, excess_authorized=authorize_excess, operation_id=new_uuid())

    @_dispatches
    def reject_expense(self, expense_request_id: str, *, reason: str) -> None:
        actor = self._actor(P.EXPENSE_APPROVE)
        self._uc["approve_expense"].reject(
            self._conn(), expense_request_id=expense_request_id, approver_id=actor,
            reason=reason, operation_id=new_uuid())

    @_dispatches
    def accrue_expense(self, expense_request_id: str, *, document_reference: str,
                       amount: str | None = None, supplier_id: str | None = None,
                       due_date: date | None = None,
                       paid_from_treasury_account_id: str | None = None) -> str:
        actor = self._actor(P.EXPENSE_ACCRUE)
        return self._uc["accrue_expense"].execute(
            self._conn(), expense_request_id=expense_request_id,
            document_reference=document_reference, accrual_date=self._today(),
            amount=amount, supplier_id=supplier_id, due_date=due_date,
            paid_from_treasury_account_id=paid_from_treasury_account_id,
            operation_id=new_uuid(), accrued_by=actor)

    @_dispatches
    def cancel_expense(self, expense_request_id: str, *, reason: str) -> None:
        actor = self._actor(P.EXPENSE_REQUEST)
        self._uc["cancel_expense"].execute(
            self._conn(), expense_request_id=expense_request_id, reason=reason,
            operation_id=new_uuid(), cancelled_by=actor)

    @_dispatches
    def create_expense_rule(self, **rule):
        actor = self._actor(P.SETTINGS_MANAGE)
        return self._uc["expense_rules"].create(self._conn(), operation_id=new_uuid(),
                                                created_by=actor, **rule)

    # ── activos ──────────────────────────────────────────────────────────
    @_dispatches
    def capitalize_asset(self, **asset):
        actor = self._actor(P.ASSET_MANAGE)
        return self._uc["capitalize_asset"].execute(
            self._conn(), capitalization_date=asset.pop("capitalization_date", None)
            or self._today(), operation_id=new_uuid(), created_by=actor, **asset)

    @_dispatches
    def run_depreciation(self, year: int, month: int) -> list[str]:
        actor = self._actor(P.ASSET_DEPRECIATE)
        return self._uc["run_depreciation"].execute(
            self._conn(), year=year, month=month, operation_id=new_uuid(), created_by=actor)

    @_dispatches
    def dispose_asset(self, asset_id: str, *, outcome: FixedAssetStatus, reason: str = "",
                      proceeds: str | None = None, treasury_account_id: str | None = None) -> str:
        actor = self._actor(P.ASSET_MANAGE)
        return self._uc["dispose_asset"].execute(
            self._conn(), asset_id=asset_id, disposal_date=self._today(), outcome=outcome,
            proceeds=proceeds, treasury_account_id=treasury_account_id, reason=reason,
            operation_id=new_uuid(), disposed_by=actor)

    @_dispatches
    def suspend_asset(self, asset_id: str, *, reason: str) -> None:
        actor = self._actor(P.ASSET_MANAGE)
        self._uc["asset_status"].suspend(self._conn(), asset_id=asset_id, reason=reason,
                                         operation_id=new_uuid(), actor=actor)

    @_dispatches
    def resume_asset(self, asset_id: str) -> None:
        actor = self._actor(P.ASSET_MANAGE)
        self._uc["asset_status"].resume(self._conn(), asset_id=asset_id,
                                        operation_id=new_uuid(), actor=actor)

    # ── configuración ────────────────────────────────────────────────────
    @_dispatches
    def update_settings(self, changes: dict, *, reason: str | None = None):
        actor = self._actor(P.SETTINGS_MANAGE)
        return self._uc["update_settings"].execute(
            self._conn(), changes=changes, operation_id=new_uuid(), updated_by=actor,
            reason=reason)

    @_dispatches
    def update_posting_profile(self, profile_id: str, *, accounts: dict[str, str],
                               effective_from: date, reason: str | None = None):
        actor = self._actor(P.SETTINGS_MANAGE)
        return self._uc["update_posting_profile"].execute(
            self._conn(), profile_id=profile_id, accounts=accounts,
            effective_from=effective_from, operation_id=new_uuid(), updated_by=actor,
            reason=reason)

    @_dispatches
    def create_dimension(self, *, kind: str, code: str, name: str,
                         branch_id: str | None = None, is_capex: bool = False,
                         org_unit_id: str | None = None):
        actor = self._actor(P.SETTINGS_MANAGE)
        conn = self._conn()
        if org_unit_id:
            # Centro de costo/utilidad de una unidad organizacional (sucursal,
            # planta, región, oficina…). Si la unidad es un sitio, su id ES el
            # `branch_id` que ya usan los asientos.
            from backend.application.organization.org_structure_service import (
                OrgStructureQueryService,
            )
            from backend.domain.finance.exceptions import FinanceDomainError
            from backend.domain.organization.org_unit import OrgUnitStatus
            unidad = OrgStructureQueryService(conn).get(org_unit_id)
            if unidad is None or unidad.status is not OrgUnitStatus.ACTIVE:
                raise FinanceDomainError("La unidad organizacional no existe o no está activa")
            if kind not in ("COST_CENTER", "PROFIT_CENTER"):
                raise FinanceDomainError("Sólo los centros de costo y de utilidad se asignan a "
                                         "una unidad organizacional")
            if unidad.unit_type.is_operating_site:
                branch_id = branch_id or unidad.id
        return self._uc["dimensions"].create(
            conn, kind=kind, code=code, name=name, branch_id=branch_id,
            is_capex=is_capex, operation_id=new_uuid(), created_by=actor,
            org_unit_id=org_unit_id or None)

    @_dispatches
    def create_tax_code(self, *, code: str, name: str, kind: TaxKind, direction: TaxDirection,
                        rate_percent: str, effective_from: date, account_id: str):
        actor = self._actor(P.SETTINGS_MANAGE)
        return self._uc["taxes"].create_code(
            self._conn(), code=code, name=name, kind=kind, direction=direction,
            rate_percent=rate_percent, effective_from=effective_from, account_id=account_id,
            operation_id=new_uuid(), created_by=actor)

    @_dispatches
    def register_exchange_rate(self, *, from_currency: str, to_currency: str, rate: str,
                               effective_date: date, source: str = ""):
        actor = self._actor(P.SETTINGS_MANAGE)
        return self._uc["currencies"].register_rate(
            self._conn(), from_currency=from_currency, to_currency=to_currency, rate=rate,
            effective_date=effective_date, source=source, operation_id=new_uuid(),
            created_by=actor)

    # ── exportación auditada (§25) ───────────────────────────────────────
    @_dispatches
    def record_export(self, *, what: str, file_name: str, rows: int) -> None:
        actor = self._actor(P.EXPORT)
        self._uc["audit_export"](self._conn(), action=AuditAction.DATA_EXPORTED, what=what,
                                 file_name=file_name, rows=rows, user_id=actor)
