"""Budget entities — approved spending plans with commitment/accrual/payment control (§16).

Cada peso de una partida está en exactamente un estado:

    aprobado − comprometido − devengado − pagado = disponible

- comprometido: solicitud de gasto aprobada, aún sin documento;
- devengado: documento recibido (factura/obligación), aún sin pagar;
- pagado: liquidado.

El presupuesto no se controla sólo contra pagos: un compromiso ya consume.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.finance.enums import BudgetStatus, CONTROLLING_BUDGET_STATUSES
from backend.domain.finance.exceptions import BudgetControlError, FinanceDomainError
from backend.domain.finance.value_objects.money import Money
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class BudgetLine:
    id: str
    budget_id: str
    account_id: str
    period_code: str            # "YYYY-MM"
    planned_amount: Money
    committed_amount: Money
    accrued_amount: Money
    cost_center_id: str | None = None
    branch_id: str | None = None
    paid_amount: Money | None = None
    profit_center_id: str | None = None
    project_id: str | None = None
    department_id: str | None = None

    def __post_init__(self) -> None:
        if self.paid_amount is None:
            self.paid_amount = Money.zero(self.planned_amount.currency_code)

    @classmethod
    def create(cls, budget_id: str, account_id: str, period_code: str, planned_amount: Money,
               *, cost_center_id: str | None = None, branch_id: str | None = None,
               profit_center_id: str | None = None, project_id: str | None = None,
               department_id: str | None = None) -> "BudgetLine":
        if planned_amount.is_negative():
            raise FinanceDomainError("El importe presupuestado no puede ser negativo")
        zero = Money.zero(planned_amount.currency_code)
        return cls(
            id=new_uuid(), budget_id=budget_id, account_id=account_id,
            period_code=period_code, planned_amount=planned_amount,
            committed_amount=zero, accrued_amount=zero, paid_amount=zero,
            cost_center_id=cost_center_id, branch_id=branch_id,
            profit_center_id=profit_center_id, project_id=project_id,
            department_id=department_id,
        )

    def consumed(self) -> Money:
        return self.committed_amount.add(self.accrued_amount).add(self.paid_amount)

    def available(self) -> Money:
        return self.planned_amount.subtract(self.consumed())

    def matches(self, *, account_id: str, period_code: str, cost_center_id: str | None = None,
                project_id: str | None = None, department_id: str | None = None,
                profit_center_id: str | None = None) -> bool:
        return (self.account_id == account_id and self.period_code == period_code
                and (self.cost_center_id or None) == (cost_center_id or None)
                and (self.project_id or None) == (project_id or None)
                and (self.department_id or None) == (department_id or None)
                and (self.profit_center_id or None) == (profit_center_id or None))

    # ── movimientos entre estados ────────────────────────────────────────
    def commit(self, amount: Money) -> None:
        if not amount.is_positive():
            raise FinanceDomainError("El compromiso debe ser mayor que cero")
        self.committed_amount = self.committed_amount.add(amount)

    def release_commitment(self, amount: Money) -> None:
        if amount > self.committed_amount:
            raise BudgetControlError("No se libera más de lo comprometido")
        self.committed_amount = self.committed_amount.subtract(amount)

    def accrue(self, amount: Money, *, from_commitment: Money | None = None) -> None:
        """Devenga ``amount``; ``from_commitment`` es lo que estaba comprometido
        por ese mismo gasto (se libera del compromiso al devengar)."""
        if not amount.is_positive():
            raise FinanceDomainError("El devengo debe ser mayor que cero")
        if from_commitment is not None and from_commitment.is_positive():
            self.release_commitment(from_commitment)
        self.accrued_amount = self.accrued_amount.add(amount)

    def pay(self, amount: Money) -> None:
        if not amount.is_positive():
            raise FinanceDomainError("El pago debe ser mayor que cero")
        if amount > self.accrued_amount:
            raise BudgetControlError("No se paga más de lo devengado pendiente")
        self.accrued_amount = self.accrued_amount.subtract(amount)
        self.paid_amount = self.paid_amount.add(amount)


@dataclass(slots=True)
class Budget:
    id: str
    name: str
    fiscal_year: int
    version: int
    operation_id: str
    status: BudgetStatus = BudgetStatus.DRAFT
    approved_by: str | None = None
    approved_at: str | None = None
    submitted_by: str | None = None
    branch_id: str | None = None
    lines: list[BudgetLine] = field(default_factory=list)
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)
    row_version: int = 0  # control optimista (auditoría F18)
    #: Control BLOQUEANTE: exceder la partida exige autorización expresa.
    #: Falso = sólo advierte (el exceso se registra y publica BUDGET_EXCEEDED).
    blocking: bool = True
    #: Versión anterior de la que nace esta (una versión nueva no edita la aprobada).
    previous_version_id: str | None = None
    rejection_reason: str | None = None
    cancel_reason: str | None = None

    @classmethod
    def create(cls, name: str, fiscal_year: int, operation_id: str, *,
               version: int = 1, branch_id: str | None = None, blocking: bool = True,
               previous_version_id: str | None = None) -> "Budget":
        if not name or not name.strip():
            raise FinanceDomainError("El presupuesto requiere nombre")
        return cls(
            id=new_uuid(), name=name.strip(), fiscal_year=fiscal_year,
            version=version, operation_id=operation_id, branch_id=branch_id,
            blocking=bool(blocking), previous_version_id=previous_version_id,
        )

    @property
    def controls_spending(self) -> bool:
        return self.status in CONTROLLING_BUDGET_STATUSES

    def add_line(self, account_id: str, period_code: str, planned_amount: Money, **kwargs) -> BudgetLine:
        if self.status is not BudgetStatus.DRAFT:
            raise FinanceDomainError(
                f"Un presupuesto {self.status.value} no se modifica; cree una nueva versión")
        line = BudgetLine.create(self.id, account_id, period_code, planned_amount, **kwargs)
        for existing in self.lines:
            if existing.matches(account_id=account_id, period_code=period_code,
                                cost_center_id=line.cost_center_id,
                                project_id=line.project_id, department_id=line.department_id,
                                profit_center_id=line.profit_center_id):
                raise FinanceDomainError("La partida ya existe en este presupuesto")
        self.lines.append(line)
        return line

    def submit(self, submitted_by: str) -> None:
        if self.status is not BudgetStatus.DRAFT:
            raise FinanceDomainError(f"No se envía un presupuesto {self.status.value}")
        if not self.lines:
            raise FinanceDomainError("No se envía un presupuesto sin partidas")
        self.status = BudgetStatus.SUBMITTED
        self.submitted_by = submitted_by
        self.rejection_reason = None
        self.updated_at = _utcnow()

    def approve(self, approved_by: str) -> None:
        if self.status is not BudgetStatus.SUBMITTED:
            raise FinanceDomainError(f"No se aprueba un presupuesto {self.status.value}")
        if self.submitted_by and approved_by == self.submitted_by:
            raise FinanceDomainError(
                "Segregación de funciones: quien envía el presupuesto no lo aprueba")
        self.status = BudgetStatus.APPROVED
        self.approved_by = approved_by
        self.approved_at = _utcnow()
        self.updated_at = self.approved_at

    def reject(self, reason: str) -> None:
        """Vuelve a borrador con el motivo: se corrige y se vuelve a enviar."""
        if self.status is not BudgetStatus.SUBMITTED:
            raise FinanceDomainError(f"No se rechaza un presupuesto {self.status.value}")
        if not (reason or "").strip():
            raise FinanceDomainError("Rechazar un presupuesto exige el motivo")
        self.status = BudgetStatus.DRAFT
        self.rejection_reason = reason.strip()
        self.updated_at = _utcnow()

    def activate(self) -> None:
        if self.status is not BudgetStatus.APPROVED:
            raise FinanceDomainError(f"Sólo se activa un presupuesto aprobado ({self.status.value})")
        self.status = BudgetStatus.ACTIVE
        self.updated_at = _utcnow()

    def close(self) -> None:
        if self.status not in CONTROLLING_BUDGET_STATUSES:
            raise FinanceDomainError(f"No se cierra un presupuesto {self.status.value}")
        self.status = BudgetStatus.CLOSED
        self.updated_at = _utcnow()

    def cancel(self, reason: str) -> None:
        if self.status in (BudgetStatus.CLOSED, BudgetStatus.CANCELLED):
            raise FinanceDomainError(f"No se cancela un presupuesto {self.status.value}")
        if not (reason or "").strip():
            raise FinanceDomainError("Cancelar un presupuesto exige el motivo")
        if any(line.consumed().is_positive() for line in self.lines):
            raise FinanceDomainError(
                "El presupuesto ya tiene compromisos o gasto; ciérrelo en lugar de cancelarlo")
        self.status = BudgetStatus.CANCELLED
        self.cancel_reason = reason.strip()
        self.updated_at = _utcnow()
