"""Solicitud de gasto y su flujo de aprobación configurable (§16).

    ExpenseRequest  → ExpenseApproval(es) → documento (devengo) → liquidación (pago)

El número de aprobaciones lo decide la regla vigente que aplique por importe,
sucursal, categoría, centro de costo y solicitante (``ExpenseApprovalRule``);
sin regla aplicable basta una aprobación. Quien solicita nunca aprueba, y dos
aprobaciones son de dos personas distintas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.finance.enums import ExpenseRequestStatus
from backend.domain.finance.exceptions import (
    ExpenseNotAuthorizedError,
    FinanceDomainError,
    SegregationOfDutiesError,
)
from backend.domain.finance.value_objects.money import Money
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class ExpenseApprovalRule:
    id: str
    name: str
    min_amount: Decimal
    required_approvals: int
    branch_id: str | None = None
    category: str | None = None
    cost_center_id: str | None = None
    requester_id: str | None = None
    priority: int = 0
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, name: str, *, min_amount: Decimal | str, required_approvals: int,
               branch_id: str | None = None, category: str | None = None,
               cost_center_id: str | None = None, requester_id: str | None = None,
               priority: int = 0) -> "ExpenseApprovalRule":
        if not (name or "").strip():
            raise FinanceDomainError("La regla de aprobación requiere nombre")
        if isinstance(min_amount, float):
            raise FinanceDomainError("El importe mínimo no se captura como float")
        amount = Decimal(str(min_amount))
        if amount < 0:
            raise FinanceDomainError("El importe mínimo no puede ser negativo")
        if not 1 <= int(required_approvals) <= 3:
            raise FinanceDomainError("Una regla exige de 1 a 3 aprobaciones")
        return cls(id=new_uuid(), name=name.strip(), min_amount=amount,
                   required_approvals=int(required_approvals), branch_id=branch_id,
                   category=(category or "").strip().upper() or None,
                   cost_center_id=cost_center_id, requester_id=requester_id,
                   priority=int(priority))

    def applies_to(self, *, amount: Money, branch_id: str | None, category: str | None,
                   cost_center_id: str | None, requester_id: str | None) -> bool:
        if not self.active or amount.amount < self.min_amount:
            return False
        if self.branch_id and self.branch_id != branch_id:
            return False
        if self.category and self.category != (category or "").strip().upper():
            return False
        if self.cost_center_id and self.cost_center_id != cost_center_id:
            return False
        if self.requester_id and self.requester_id != requester_id:
            return False
        return True


class ExpenseApprovalPolicy:
    """Elige cuántas aprobaciones exige una solicitud."""

    @staticmethod
    def required_approvals(rules: list[ExpenseApprovalRule], **context) -> int:
        matching = [rule for rule in rules if rule.applies_to(**context)]
        if not matching:
            return 1
        best = max(matching, key=lambda rule: (rule.priority, rule.required_approvals))
        return best.required_approvals


@dataclass(slots=True)
class ExpenseApproval:
    id: str
    expense_request_id: str
    approver_id: str
    decision: str
    reason: str = ""
    decided_at: str = field(default_factory=_utcnow)


@dataclass(slots=True)
class ExpenseRequest:
    id: str
    account_id: str
    period_code: str
    amount: Money
    requested_by: str
    operation_id: str
    budget_id: str | None = None
    category: str = ""
    description: str = ""
    cost_center_id: str | None = None
    project_id: str | None = None
    department_id: str | None = None
    branch_id: str | None = None
    supplier_id: str | None = None
    status: ExpenseRequestStatus = ExpenseRequestStatus.REQUESTED
    required_approvals: int = 1
    excess_authorized: bool = False
    accrued_amount: Money = None  # type: ignore[assignment]
    settled_amount: Money = None  # type: ignore[assignment]
    resolution_reason: str | None = None
    payable_id: str | None = None
    accrual_journal_entry_id: str | None = None
    document_reference: str | None = None
    approvals: list[ExpenseApproval] = field(default_factory=list)
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        zero = Money.zero(self.amount.currency_code)
        if self.accrued_amount is None:
            self.accrued_amount = zero
        if self.settled_amount is None:
            self.settled_amount = zero

    @classmethod
    def create(cls, *, account_id: str, period_code: str, amount: Money, requested_by: str,
               operation_id: str, required_approvals: int = 1, budget_id: str | None = None,
               category: str = "", description: str = "", cost_center_id: str | None = None,
               project_id: str | None = None, department_id: str | None = None,
               branch_id: str | None = None,
               supplier_id: str | None = None) -> "ExpenseRequest":
        if not amount.is_positive():
            raise FinanceDomainError("La solicitud de gasto debe ser mayor que cero")
        if not (requested_by or "").strip():
            raise FinanceDomainError("La solicitud requiere al solicitante")
        if not 1 <= int(required_approvals) <= 3:
            raise FinanceDomainError("Una solicitud exige de 1 a 3 aprobaciones")
        return cls(id=new_uuid(), account_id=account_id, period_code=period_code,
                   amount=amount, requested_by=requested_by.strip(), operation_id=operation_id,
                   required_approvals=int(required_approvals), budget_id=budget_id,
                   category=(category or "").strip().upper(),
                   description=(description or "").strip(), cost_center_id=cost_center_id,
                   project_id=project_id, department_id=department_id,
                   branch_id=branch_id, supplier_id=supplier_id)

    def approval_count(self) -> int:
        return sum(1 for a in self.approvals if a.decision == "APPROVED")

    def approve(self, approver_id: str, reason: str = "") -> bool:
        """Registra una aprobación; devuelve ``True`` si con ella queda APROBADA."""
        if self.status is not ExpenseRequestStatus.REQUESTED:
            raise FinanceDomainError(f"No se aprueba una solicitud {self.status.value}")
        who = (approver_id or "").strip()
        if not who:
            raise FinanceDomainError("La aprobación requiere al aprobador")
        if who == self.requested_by:
            raise SegregationOfDutiesError("Quien solicita un gasto no lo aprueba")
        if any(a.approver_id == who for a in self.approvals):
            raise SegregationOfDutiesError(
                "Cada aprobación la da una persona distinta; usted ya aprobó")
        self.approvals.append(ExpenseApproval(new_uuid(), self.id, who, "APPROVED",
                                              (reason or "").strip()))
        if self.approval_count() >= self.required_approvals:
            self.status = ExpenseRequestStatus.APPROVED
        self.updated_at = _utcnow()
        return self.status is ExpenseRequestStatus.APPROVED

    def reject(self, approver_id: str, reason: str) -> None:
        if self.status is not ExpenseRequestStatus.REQUESTED:
            raise FinanceDomainError(f"No se rechaza una solicitud {self.status.value}")
        if not (reason or "").strip():
            raise FinanceDomainError("Rechazar un gasto exige el motivo")
        if (approver_id or "").strip() == self.requested_by:
            raise SegregationOfDutiesError("Quien solicita un gasto no lo rechaza por otros")
        self.approvals.append(ExpenseApproval(new_uuid(), self.id, approver_id.strip(),
                                              "REJECTED", reason.strip()))
        self.status = ExpenseRequestStatus.REJECTED
        self.resolution_reason = reason.strip()
        self.updated_at = _utcnow()

    def accrue(self, amount: Money, document_reference: str, *,
               payable_id: str | None = None, journal_entry_id: str | None = None) -> None:
        if self.status is not ExpenseRequestStatus.APPROVED:
            raise ExpenseNotAuthorizedError(
                "Sólo se devenga un gasto aprobado (falta aprobación)")
        if not (document_reference or "").strip():
            raise FinanceDomainError("El devengo exige la referencia del documento")
        if not amount.is_positive():
            raise FinanceDomainError("El importe devengado debe ser mayor que cero")
        self.accrued_amount = amount
        self.document_reference = document_reference.strip()
        self.payable_id = payable_id
        self.accrual_journal_entry_id = journal_entry_id
        self.status = ExpenseRequestStatus.ACCRUED
        self.updated_at = _utcnow()

    def settle(self, amount: Money) -> None:
        if self.status is not ExpenseRequestStatus.ACCRUED:
            raise ExpenseNotAuthorizedError("Sólo se liquida un gasto devengado")
        settled = self.settled_amount.add(amount)
        if settled > self.accrued_amount:
            raise FinanceDomainError("La liquidación excede lo devengado")
        self.settled_amount = settled
        if settled == self.accrued_amount:
            self.status = ExpenseRequestStatus.SETTLED
        self.updated_at = _utcnow()

    def cancel(self, reason: str) -> None:
        if self.status not in (ExpenseRequestStatus.REQUESTED, ExpenseRequestStatus.APPROVED):
            raise FinanceDomainError(f"No se cancela una solicitud {self.status.value}")
        if not (reason or "").strip():
            raise FinanceDomainError("Cancelar un gasto exige el motivo")
        self.status = ExpenseRequestStatus.CANCELLED
        self.resolution_reason = reason.strip()
        self.updated_at = _utcnow()
