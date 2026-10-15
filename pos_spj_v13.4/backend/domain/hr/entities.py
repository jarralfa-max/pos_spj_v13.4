"""HR domain entities. All identities are UUIDv7 strings."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone

from backend.domain.hr.enums import (
    AdjustmentStatus,
    AttendanceIncidentType,
    AttendanceSource,
    ContractType,
    EmploymentStatus,
    LeaveStatus,
    LeaveType,
    PaymentFrequency,
    PaymentMethod,
    PayrollConcept,
    PayrollRunStatus,
    PunchType,
    WorkdayStatus,
)
from backend.domain.hr.exceptions import (
    AttendanceInvalidSequenceError,
    HRDomainError,
    InvalidAdjustmentStateError,
    InvalidLeaveDatesError,
    InvalidLeaveStateError,
    PayrollAlreadyPaidError,
    PayrollInvalidStateError,
)
from backend.domain.hr.value_objects import Money
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Catalogs ──────────────────────────────────────────────────────────────
@dataclass(slots=True)
class Department:
    id: str
    code: str
    name: str
    branch_id: str | None = None
    active: bool = True
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, code: str, name: str, *, branch_id: str | None = None) -> "Department":
        if not code or not name:
            raise HRDomainError("Department requiere code y name")
        return cls(id=new_uuid(), code=code.strip(), name=name.strip(), branch_id=branch_id)


@dataclass(slots=True)
class Position:
    id: str
    code: str
    name: str
    department_id: str | None = None
    active: bool = True
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, code: str, name: str, *, department_id: str | None = None) -> "Position":
        if not code or not name:
            raise HRDomainError("Position requiere code y name")
        return cls(id=new_uuid(), code=code.strip(), name=name.strip(),
                   department_id=department_id)


# ── Employee ──────────────────────────────────────────────────────────────
@dataclass(slots=True)
class Employee:
    id: str
    employee_code: str
    first_name: str
    last_name: str
    branch_id: str
    employment_status: EmploymentStatus
    contract_type: ContractType
    payment_frequency: PaymentFrequency
    base_salary: Money
    daily_salary: Money
    hire_date: date
    phone_e164: str | None = None
    email: str | None = None
    department_id: str | None = None
    position_id: str | None = None
    supervisor_employee_id: str | None = None
    termination_date: date | None = None
    termination_reason: str | None = None
    bank_account_reference: str | None = None
    tax_identifier: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls,
        employee_code: str,
        first_name: str,
        last_name: str,
        branch_id: str,
        contract_type: ContractType,
        payment_frequency: PaymentFrequency,
        base_salary: Money,
        daily_salary: Money,
        hire_date: date,
        **kwargs,
    ) -> "Employee":
        if not employee_code or not employee_code.strip():
            raise HRDomainError("Employee requiere employee_code")
        if not first_name or not last_name:
            raise HRDomainError("Employee requiere first_name y last_name")
        if not branch_id:
            raise HRDomainError("Employee requiere branch_id")
        if base_salary.is_negative() or daily_salary.is_negative():
            raise HRDomainError("Los salarios no pueden ser negativos")
        return cls(
            id=new_uuid(), employee_code=employee_code.strip(),
            first_name=first_name.strip(), last_name=last_name.strip(),
            branch_id=branch_id, employment_status=EmploymentStatus.ACTIVE,
            contract_type=contract_type, payment_frequency=payment_frequency,
            base_salary=base_salary, daily_salary=daily_salary, hire_date=hire_date,
            **kwargs,
        )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def assert_active(self) -> None:
        from backend.domain.hr.exceptions import EmployeeInactiveError
        if not self.active or self.employment_status is EmploymentStatus.TERMINATED:
            raise EmployeeInactiveError(f"Empleado {self.employee_code} inactivo")

    def deactivate(self, *, termination_date: date, reason: str) -> None:
        if not reason or not reason.strip():
            raise HRDomainError("La baja requiere un motivo")
        self.active = False
        self.employment_status = EmploymentStatus.TERMINATED
        self.termination_date = termination_date
        self.termination_reason = reason.strip()
        self.updated_at = _utcnow()

    def touch(self) -> None:
        self.updated_at = _utcnow()

    #: Campos del expediente que se editan sin vigencia (HR-23). El salario
    #: va por ``change_salary`` porque tiene historia.
    EDITABLE_FIELDS = (
        "first_name", "last_name", "phone_e164", "email", "department_id",
        "position_id", "supervisor_employee_id", "bank_account_reference",
        "tax_identifier", "emergency_contact_name", "emergency_contact_phone",
    )

    def update_profile(self, **fields) -> dict:
        """Aplica cambios del expediente con LAS MISMAS invariantes del alta
        (auditoría HR-23: la edición hacía ``setattr`` y aceptaba un nombre
        vacío). Devuelve ``{campo: (antes, después)}`` para la bitácora."""
        changes: dict = {}
        for key, value in fields.items():
            if key not in self.EDITABLE_FIELDS or value is None:
                continue
            if key in ("first_name", "last_name"):
                value = str(value).strip()
                if not value:
                    raise HRDomainError("El nombre y los apellidos no pueden quedar vacíos")
            elif isinstance(value, str):
                value = value.strip() or None
            if getattr(self, key) != value:
                changes[key] = (getattr(self, key), value)
                setattr(self, key, value)
        if changes:
            self.touch()
        return changes

    def change_salary(self, *, daily_salary: Money, base_salary: Money) -> None:
        if daily_salary.is_negative() or base_salary.is_negative():
            raise HRDomainError("Los salarios no pueden ser negativos")
        self.daily_salary = daily_salary
        self.base_salary = base_salary
        self.touch()

    def is_employed_on(self, day: date) -> bool:
        """HR-09: elegibilidad por VIGENCIA del vínculo, no por el estado de
        hoy — una baja futura conserva el historial; un alta posterior no
        cobra un periodo previo."""
        if day < self.hire_date:
            return False
        return self.termination_date is None or day <= self.termination_date


# ── Attendance ────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class AttendancePunch:
    """An immutable attendance mark (ENTRY/EXIT). Never overwritten.

    ``frozen`` enforces immutability at the language level: any attempt to
    reassign a field raises ``FrozenInstanceError``. Corrections must go through
    an ``AttendanceAdjustment`` instead of mutating the original punch.
    """

    id: str
    employee_id: str
    branch_id: str
    punch_type: PunchType
    occurred_at: datetime
    source: AttendanceSource
    operation_id: str
    timezone_name: str = "America/Mexico_City"
    source_reference_id: str | None = None
    device_id: str | None = None
    registered_by_user_id: str | None = None
    notes: str | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, employee_id: str, branch_id: str, punch_type: PunchType,
               occurred_at: datetime, source: AttendanceSource, operation_id: str,
               **kwargs) -> "AttendancePunch":
        if not employee_id or not branch_id:
            raise HRDomainError("La marcación requiere employee_id y branch_id")
        if not operation_id:
            raise HRDomainError("La marcación requiere operation_id")
        return cls(id=new_uuid(), employee_id=employee_id, branch_id=branch_id,
                   punch_type=punch_type, occurred_at=occurred_at, source=source,
                   operation_id=operation_id, **kwargs)


@dataclass(slots=True)
class AttendanceWorkday:
    """Calculated workday aggregating punches for one employee/date."""

    id: str
    employee_id: str
    branch_id: str
    work_date: date
    status: WorkdayStatus
    scheduled_shift_id: str | None = None
    first_entry_at: datetime | None = None
    last_exit_at: datetime | None = None
    worked_minutes: int = 0
    late_minutes: int = 0
    overtime_minutes: int = 0
    incident_type: AttendanceIncidentType | None = None
    calculation_version: int = 1
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, employee_id: str, branch_id: str, work_date: date,
               *, scheduled_shift_id: str | None = None) -> "AttendanceWorkday":
        return cls(id=new_uuid(), employee_id=employee_id, branch_id=branch_id,
                   work_date=work_date, status=WorkdayStatus.OPEN,
                   scheduled_shift_id=scheduled_shift_id)

    def has_open_entry(self) -> bool:
        return self.first_entry_at is not None and self.last_exit_at is None


@dataclass(slots=True)
class AttendanceAdjustment:
    """A requested correction to attendance; never edits the original punch."""

    id: str
    employee_id: str
    workday_id: str
    field_name: str            # e.g. "first_entry_at" / "last_exit_at"
    previous_value: str | None
    requested_value: str
    reason: str
    requested_by_user_id: str
    operation_id: str
    original_punch_id: str | None = None
    status: AdjustmentStatus = AdjustmentStatus.PENDING
    approved_by_user_id: str | None = None
    approved_at: str | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, employee_id: str, workday_id: str, field_name: str,
               previous_value: str | None, requested_value: str, reason: str,
               requested_by_user_id: str, operation_id: str,
               *, original_punch_id: str | None = None) -> "AttendanceAdjustment":
        if not reason or not reason.strip():
            raise HRDomainError("El ajuste de asistencia requiere motivo")
        if not requested_by_user_id:
            raise HRDomainError("El ajuste requiere el usuario solicitante")
        return cls(id=new_uuid(), employee_id=employee_id, workday_id=workday_id,
                   field_name=field_name, previous_value=previous_value,
                   requested_value=requested_value, reason=reason.strip(),
                   requested_by_user_id=requested_by_user_id, operation_id=operation_id,
                   original_punch_id=original_punch_id)

    def approve(self, approver_user_id: str) -> None:
        if self.status is not AdjustmentStatus.PENDING:
            raise InvalidAdjustmentStateError(f"Ajuste en estado {self.status.value}")
        if not approver_user_id:
            raise HRDomainError("La aprobación requiere el usuario aprobador")
        if approver_user_id == self.requested_by_user_id:
            raise HRDomainError("Separación de funciones: el solicitante no puede aprobar su ajuste")
        self.status = AdjustmentStatus.APPROVED
        self.approved_by_user_id = approver_user_id
        self.approved_at = _utcnow()

    def reject(self, approver_user_id: str) -> None:
        if self.status is not AdjustmentStatus.PENDING:
            raise InvalidAdjustmentStateError(f"Ajuste en estado {self.status.value}")
        self.status = AdjustmentStatus.REJECTED
        self.approved_by_user_id = approver_user_id
        self.approved_at = _utcnow()


# ── Work shifts ───────────────────────────────────────────────────────────
@dataclass(slots=True)
class WorkShift:
    id: str
    name: str
    start_time: time
    end_time: time
    crosses_midnight: bool
    break_minutes: int = 0
    late_tolerance_minutes: int = 0
    branch_id: str | None = None
    active: bool = True
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, name: str, start_time: time, end_time: time,
               *, break_minutes: int = 0, late_tolerance_minutes: int = 0,
               branch_id: str | None = None) -> "WorkShift":
        if not name or not name.strip():
            raise HRDomainError("WorkShift requiere name")
        if break_minutes < 0 or late_tolerance_minutes < 0:
            raise HRDomainError("break/tolerance no pueden ser negativos")
        return cls(id=new_uuid(), name=name.strip(), start_time=start_time,
                   end_time=end_time, crosses_midnight=end_time <= start_time,
                   break_minutes=break_minutes,
                   late_tolerance_minutes=late_tolerance_minutes, branch_id=branch_id)

    def span_minutes(self) -> int:
        start = self.start_time.hour * 60 + self.start_time.minute
        end = self.end_time.hour * 60 + self.end_time.minute
        if self.crosses_midnight:
            end += 24 * 60
        return max(0, end - start)

    def expected_minutes(self) -> int:
        """Minutos NETOS esperados: el descanso configurado es NO pagado
        (HR-15) y se descuenta igual del esperado y del trabajado."""
        return max(0, self.span_minutes() - self.break_minutes)


@dataclass(slots=True)
class ShiftAssignment:
    id: str
    employee_id: str
    work_shift_id: str
    effective_from: date
    weekdays: tuple[int, ...]
    branch_id: str | None = None
    effective_to: date | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, employee_id: str, work_shift_id: str, effective_from: date,
               weekdays: tuple[int, ...], *, branch_id: str | None = None,
               effective_to: date | None = None) -> "ShiftAssignment":
        if not weekdays or any(d < 0 or d > 6 for d in weekdays):
            raise HRDomainError("weekdays inválidos (0=lunes … 6=domingo)")
        if effective_to is not None and effective_to < effective_from:
            raise HRDomainError("effective_to no puede ser anterior a effective_from")
        return cls(id=new_uuid(), employee_id=employee_id, work_shift_id=work_shift_id,
                   effective_from=effective_from, weekdays=tuple(sorted(set(weekdays))),
                   branch_id=branch_id, effective_to=effective_to)


# ── Leave ─────────────────────────────────────────────────────────────────
@dataclass(slots=True)
class LeaveRequest:
    id: str
    employee_id: str
    branch_id: str
    leave_type: LeaveType
    start_date: date
    end_date: date
    requested_days: int
    reason: str
    requested_by_user_id: str
    operation_id: str
    status: LeaveStatus = LeaveStatus.PENDING
    approved_by_user_id: str | None = None
    approved_at: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)
    cancelled_by_user_id: str | None = None
    cancelled_at: str | None = None
    cancel_reason: str | None = None

    @classmethod
    def create(cls, employee_id: str, branch_id: str, leave_type: LeaveType,
               start_date: date, end_date: date, reason: str,
               requested_by_user_id: str, operation_id: str,
               *, status: LeaveStatus = LeaveStatus.PENDING) -> "LeaveRequest":
        if end_date < start_date:
            raise InvalidLeaveDatesError("end_date no puede ser anterior a start_date")
        if not reason or not reason.strip():
            raise HRDomainError("La solicitud requiere motivo")
        requested_days = (end_date - start_date).days + 1
        return cls(id=new_uuid(), employee_id=employee_id, branch_id=branch_id,
                   leave_type=leave_type, start_date=start_date, end_date=end_date,
                   requested_days=requested_days, reason=reason.strip(),
                   requested_by_user_id=requested_by_user_id, operation_id=operation_id,
                   status=status)

    def overlaps(self, other_start: date, other_end: date) -> bool:
        return self.start_date <= other_end and other_start <= self.end_date

    def covers(self, day: date) -> bool:
        return self.start_date <= day <= self.end_date

    def approve(self, approver_user_id: str, *, is_self: bool = False,
                self_approval_allowed: bool = False) -> None:
        if self.status not in (LeaveStatus.PENDING, LeaveStatus.DRAFT):
            raise InvalidLeaveStateError(f"Solicitud en estado {self.status.value}")
        if not approver_user_id:
            raise HRDomainError("La aprobación requiere el usuario aprobador")
        # HR-19: quien pide (o el propio empleado) no aprueba su ausencia salvo
        # facultad expresa (``RRHH.permiso.autoaprobar``).
        if (is_self or approver_user_id == self.requested_by_user_id) \
                and not self_approval_allowed:
            raise HRDomainError(
                "Separación de funciones: el solicitante no aprueba su propia ausencia")
        self.status = LeaveStatus.APPROVED
        self.approved_by_user_id = approver_user_id
        self.approved_at = _utcnow()
        self.updated_at = self.approved_at

    def reject(self, approver_user_id: str) -> None:
        if self.status not in (LeaveStatus.PENDING, LeaveStatus.DRAFT):
            raise InvalidLeaveStateError(f"Solicitud en estado {self.status.value}")
        self.status = LeaveStatus.REJECTED
        self.approved_by_user_id = approver_user_id
        self.approved_at = _utcnow()
        self.updated_at = self.approved_at

    def cancel(self, actor_user_id: str | None = None, *, reason: str | None = None) -> None:
        if self.status in (LeaveStatus.REJECTED, LeaveStatus.CANCELLED):
            raise InvalidLeaveStateError(f"No se puede cancelar en estado {self.status.value}")
        if self.status is LeaveStatus.APPROVED and not (reason and reason.strip()):
            raise HRDomainError("Cancelar una ausencia aprobada requiere un motivo")
        self.status = LeaveStatus.CANCELLED
        self.cancelled_by_user_id = actor_user_id
        self.cancel_reason = reason.strip() if reason else None
        self.cancelled_at = _utcnow()
        self.updated_at = self.cancelled_at


# ── Payroll ───────────────────────────────────────────────────────────────
@dataclass(slots=True)
class PayrollLine:
    id: str
    payroll_run_id: str
    employee_id: str
    concept: PayrollConcept
    amount: Money
    is_deduction: bool
    quantity: str = "1"
    notes: str = ""

    @classmethod
    def create(cls, payroll_run_id: str, employee_id: str, concept: PayrollConcept,
               amount: Money, *, is_deduction: bool, quantity: str = "1",
               notes: str = "") -> "PayrollLine":
        if amount.is_negative():
            raise HRDomainError("El importe de la línea no puede ser negativo (use is_deduction)")
        return cls(id=new_uuid(), payroll_run_id=payroll_run_id, employee_id=employee_id,
                   concept=concept, amount=amount, is_deduction=is_deduction,
                   quantity=quantity, notes=notes)


@dataclass(slots=True)
class PayrollPayment:
    id: str
    payroll_run_id: str
    net_amount: Money
    gross_amount: Money
    deductions_amount: Money
    payment_method: PaymentMethod
    operation_id: str
    paid_by_user_id: str
    authorized_by_user_id: str
    employee_ids: tuple[str, ...] = ()
    paid_at: str = field(default_factory=_utcnow)
    payment_reference: str | None = None


@dataclass(slots=True)
class PayrollRun:
    id: str
    period_start: date
    period_end: date
    branch_id: str | None
    operation_id: str
    status: PayrollRunStatus = PayrollRunStatus.DRAFT
    payment_frequency: PaymentFrequency | None = None
    generated_by_user_id: str | None = None
    authorized_by_user_id: str | None = None
    authorized_at: str | None = None
    paid_at: str | None = None
    payment_id: str | None = None
    lines: list[PayrollLine] = field(default_factory=list)
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)
    run_type: str = "ORDINARY"
    request_fingerprint: str | None = None
    authorized_net_amount: str | None = None
    original_run_id: str | None = None
    adjustment_reason: str | None = None
    reversed_at: str | None = None
    reversed_by_user_id: str | None = None
    reversal_reason: str | None = None

    @classmethod
    def create(cls, period_start: date, period_end: date, operation_id: str,
               *, branch_id: str | None = None,
               generated_by_user_id: str | None = None,
               payment_frequency: PaymentFrequency | None = None) -> "PayrollRun":
        if period_end < period_start:
            raise HRDomainError("period_end no puede ser anterior a period_start")
        return cls(id=new_uuid(), period_start=period_start, period_end=period_end,
                   branch_id=branch_id, operation_id=operation_id,
                   generated_by_user_id=generated_by_user_id,
                   payment_frequency=payment_frequency)

    def employee_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(line.employee_id for line in self.lines))

    def gross_amount(self) -> Money:
        total = Money.zero()
        for line in self.lines:
            if not line.is_deduction:
                total = total.add(line.amount)
        return total

    def deductions_amount(self) -> Money:
        total = Money.zero()
        for line in self.lines:
            if line.is_deduction:
                total = total.add(line.amount)
        return total

    def net_amount(self) -> Money:
        return self.gross_amount().subtract(self.deductions_amount())

    def employee_nets(self) -> dict:
        """Neto POR EMPLEADO (HR-11): lo que se entrega a cada persona."""
        nets: dict = {}
        for line in self.lines:
            current = nets.get(line.employee_id, Money.zero(line.amount.currency_code))
            nets[line.employee_id] = (current.subtract(line.amount) if line.is_deduction
                                      else current.add(line.amount))
        return nets

    def negative_employees(self) -> list:
        return [employee_id for employee_id, net in self.employee_nets().items()
                if net.is_negative()]

    def _assert_mutable(self) -> None:
        # HR-27: autorizar CONGELA el importe; cambiar líneas después exige
        # volver a generar (cancelar y regenerar), no editar lo autorizado.
        if self.status in (PayrollRunStatus.PAID, PayrollRunStatus.CANCELLED,
                           PayrollRunStatus.AUTHORIZED):
            raise PayrollInvalidStateError(
                f"La corrida está {self.status.value} y no puede modificarse"
            )

    def add_line(self, line: PayrollLine) -> None:
        self._assert_mutable()
        self.lines.append(line)
        self.updated_at = _utcnow()

    def mark_calculated(self) -> None:
        if self.status is not PayrollRunStatus.DRAFT:
            raise PayrollInvalidStateError(f"No se puede calcular en estado {self.status.value}")
        if not self.lines:
            from backend.domain.hr.exceptions import PayrollEmptyRunError
            raise PayrollEmptyRunError("La corrida no tiene líneas")
        self.status = PayrollRunStatus.CALCULATED
        self.updated_at = _utcnow()

    def authorize(self, authorizer_user_id: str) -> None:
        if self.status not in (PayrollRunStatus.CALCULATED, PayrollRunStatus.UNDER_REVIEW):
            raise PayrollInvalidStateError(f"No se puede autorizar en estado {self.status.value}")
        if self.generated_by_user_id and authorizer_user_id == self.generated_by_user_id:
            raise HRDomainError("Separación de funciones: quien genera no autoriza la nómina")
        negatives = self.negative_employees()
        if negatives:
            raise PayrollInvalidStateError(
                f"{len(negatives)} empleado(s) con neto negativo; resuélvalo antes de autorizar")
        self.status = PayrollRunStatus.AUTHORIZED
        self.authorized_by_user_id = authorizer_user_id
        self.authorized_at = _utcnow()
        self.authorized_net_amount = self.net_amount().to_string()
        self.updated_at = self.authorized_at

    def mark_paid(self, payment_id: str) -> None:
        if self.status is PayrollRunStatus.PAID:
            raise PayrollAlreadyPaidError("La corrida ya fue pagada")
        from backend.domain.hr.exceptions import PayrollNotAuthorizedError
        if self.status is not PayrollRunStatus.AUTHORIZED:
            raise PayrollNotAuthorizedError("La corrida debe estar autorizada para pagarse")
        if self.authorized_net_amount is not None \
                and self.authorized_net_amount != self.net_amount().to_string():
            raise PayrollInvalidStateError(
                "El importe cambió después de autorizar; la corrida debe autorizarse de nuevo")
        if self.negative_employees():
            raise PayrollInvalidStateError("Hay empleados con neto negativo; no se paga")
        self.status = PayrollRunStatus.PAID
        self.payment_id = payment_id
        self.paid_at = _utcnow()
        self.updated_at = self.paid_at

    def cancel(self) -> None:
        if self.status is PayrollRunStatus.PAID:
            raise PayrollAlreadyPaidError("Una corrida pagada no se cancela; requiere reverso")
        self.status = PayrollRunStatus.CANCELLED
        self.updated_at = _utcnow()

    def reverse_payment(self, actor_user_id: str, *, reason: str) -> None:
        """Pago registrado por error: la corrida queda CANCELADA con la traza del
        reverso; Finanzas revierte su asiento y los días vuelven a quedar libres."""
        if self.status is not PayrollRunStatus.PAID:
            raise PayrollInvalidStateError("Sólo se revierte el pago de una corrida pagada")
        if not reason or not reason.strip():
            raise HRDomainError("Revertir un pago de nómina requiere motivo")
        if not actor_user_id:
            raise HRDomainError("El reverso requiere el usuario que lo hace")
        self.status = PayrollRunStatus.CANCELLED
        self.reversed_at = _utcnow()
        self.reversed_by_user_id = actor_user_id
        self.reversal_reason = reason.strip()
        self.updated_at = self.reversed_at
