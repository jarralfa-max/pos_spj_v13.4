"""CASH-2 aggregate roots and immutable operational documents."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.shared.ids import new_uuid, validate_uuidv7
from backend.domain.cash_register.enums import (
    BlindCountStatus, CashDifferenceClassification, CashDifferenceSeverity,
    CashDifferenceStatus, CashHandoverStatus,
    CashMovementDirection, CashMovementType, CashShiftStatus, DeviceStatus,
)
from backend.domain.cash_register.exceptions import (
    CashDuplicateOperationError, CashInvalidStateError,
    CashSegregationOfDutiesError,
)
from backend.domain.cash_register.value_objects.money import money


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ids(*values: str) -> None:
    for value in values:
        validate_uuidv7(value)


@dataclass(slots=True)
class CashRegister:
    id: str
    branch_id: str
    name: str
    status: DeviceStatus = DeviceStatus.ACTIVE
    blocked_reason: str | None = None

    @classmethod
    def create(cls, *, branch_id: str, name: str) -> "CashRegister":
        _ids(branch_id)
        if not name.strip():
            raise ValueError("Cash register name is required")
        return cls(new_uuid(), branch_id, name.strip())

    def activate(self) -> None:
        self.status, self.blocked_reason = DeviceStatus.ACTIVE, None

    def block(self, reason: str) -> None:
        if not reason.strip():
            raise ValueError("Blocking reason is required")
        self.status, self.blocked_reason = DeviceStatus.BLOCKED, reason.strip()


@dataclass(slots=True)
class CashDrawer:
    id: str
    branch_id: str
    register_id: str
    name: str
    status: DeviceStatus = DeviceStatus.ACTIVE

    @classmethod
    def create(cls, *, branch_id: str, register_id: str, name: str) -> "CashDrawer":
        _ids(branch_id, register_id)
        if not name.strip():
            raise ValueError("Cash drawer name is required")
        return cls(new_uuid(), branch_id, register_id, name.strip())

    def activate(self) -> None:
        self.status = DeviceStatus.ACTIVE

    def block(self) -> None:
        self.status = DeviceStatus.BLOCKED

    def assign_to(self, register_id: str) -> None:
        _ids(register_id)
        self.register_id = register_id


@dataclass(slots=True)
class PosTerminal:
    id: str
    branch_id: str
    register_id: str
    name: str
    status: DeviceStatus = DeviceStatus.ACTIVE

    @classmethod
    def create(cls, *, branch_id: str, register_id: str, name: str) -> "PosTerminal":
        _ids(branch_id, register_id)
        if not name.strip():
            raise ValueError("POS terminal name is required")
        return cls(new_uuid(), branch_id, register_id, name.strip())

    def activate(self) -> None:
        self.status = DeviceStatus.ACTIVE

    def block(self) -> None:
        self.status = DeviceStatus.BLOCKED

    def assign_to(self, register_id: str) -> None:
        _ids(register_id)
        self.register_id = register_id


@dataclass(slots=True)
class CashShift:
    id: str
    branch_id: str
    register_id: str
    drawer_id: str
    terminal_id: str
    cashier_user_id: str
    opening_amount: Decimal
    opening_operation_id: str
    status: CashShiftStatus = CashShiftStatus.OPEN
    opened_at: str = field(default_factory=_now)
    suspended_reason: str | None = None
    z_cut_id: str | None = None
    closed_at: str | None = None

    @classmethod
    def open(cls, *, branch_id: str, register_id: str, drawer_id: str,
             terminal_id: str, cashier_user_id: str, opening_amount: Decimal,
             operation_id: str) -> "CashShift":
        _ids(branch_id, register_id, drawer_id, terminal_id, cashier_user_id, operation_id)
        return cls(new_uuid(), branch_id, register_id, drawer_id, terminal_id,
                   cashier_user_id, money(opening_amount), operation_id)

    def suspend(self, reason: str) -> None:
        if self.status is not CashShiftStatus.OPEN or not reason.strip():
            raise CashInvalidStateError("Only an open shift can be suspended with a reason")
        self.status, self.suspended_reason = CashShiftStatus.SUSPENDED, reason.strip()

    def resume(self) -> None:
        if self.status is not CashShiftStatus.SUSPENDED:
            raise CashInvalidStateError("Only a suspended shift can be resumed")
        self.status, self.suspended_reason = CashShiftStatus.OPEN, None

    def begin_closing(self) -> None:
        if self.status is not CashShiftStatus.OPEN:
            raise CashInvalidStateError("Only an open shift can begin closing")
        self.status = CashShiftStatus.CLOSING

    def close(self, *, z_cut_id: str) -> None:
        _ids(z_cut_id)
        if self.status is not CashShiftStatus.CLOSING or self.z_cut_id:
            raise CashInvalidStateError("Shift closing requires CLOSING state and one final Z cut")
        self.z_cut_id, self.status, self.closed_at = z_cut_id, CashShiftStatus.CLOSED, _now()


@dataclass(frozen=True, slots=True)
class CashLedgerEntry:
    id: str
    shift_id: str
    branch_id: str
    movement_type: CashMovementType
    direction: CashMovementDirection
    amount: Decimal
    operation_id: str
    recorded_by: str
    concept: str = ""
    reference_id: str | None = None
    reversal_of_id: str | None = None
    related_sale_id: str | None = None
    recorded_at: str = field(default_factory=_now)

    @classmethod
    def create(cls, *, shift_id: str, branch_id: str,
               movement_type: CashMovementType, direction: CashMovementDirection,
               amount: Decimal, operation_id: str, recorded_by: str,
               concept: str = "",
               reference_id: str | None = None,
               reversal_of_id: str | None = None,
               related_sale_id: str | None = None) -> "CashLedgerEntry":
        _ids(shift_id, branch_id, operation_id, recorded_by)
        if reference_id is not None:
            _ids(reference_id)
        if reversal_of_id is not None:
            _ids(reversal_of_id)
        if related_sale_id is not None:
            _ids(related_sale_id)
        return cls(new_uuid(), shift_id, branch_id, movement_type, direction,
                   money(amount, allow_zero=False), operation_id, recorded_by,
                   concept.strip(), reference_id, reversal_of_id, related_sale_id)

    @property
    def signed_amount(self) -> Decimal:
        return self.amount if self.direction is CashMovementDirection.INFLOW else -self.amount


@dataclass(slots=True)
class CashLedger:
    shift_id: str
    entries: list[CashLedgerEntry] = field(default_factory=list)

    def __post_init__(self) -> None:
        _ids(self.shift_id)

    def append(self, entry: CashLedgerEntry) -> None:
        if entry.shift_id != self.shift_id:
            raise CashInvalidStateError("Ledger entry belongs to another shift")
        if any(item.operation_id == entry.operation_id for item in self.entries):
            raise CashDuplicateOperationError("Duplicate cash ledger operation")
        self.entries.append(entry)

    @property
    def balance(self) -> Decimal:
        return sum((entry.signed_amount for entry in self.entries), Decimal("0"))


@dataclass(slots=True)
class BlindCashCount:
    id: str
    shift_id: str
    branch_id: str
    counter_user_id: str
    operation_id: str
    denominations: dict[Decimal, int] = field(default_factory=dict)
    status: BlindCountStatus = BlindCountStatus.OPEN
    confirmed_at: str | None = None

    @classmethod
    def start(cls, *, shift_id: str, branch_id: str, counter_user_id: str,
              operation_id: str) -> "BlindCashCount":
        _ids(shift_id, branch_id, counter_user_id, operation_id)
        return cls(new_uuid(), shift_id, branch_id, counter_user_id, operation_id)

    def capture(self, *, denomination: Decimal, quantity: int) -> None:
        if self.status is not BlindCountStatus.OPEN:
            raise CashInvalidStateError("A confirmed blind count is immutable")
        denomination = money(denomination, allow_zero=False)
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
            raise ValueError("Denomination quantity must be a non-negative integer")
        self.denominations[denomination] = quantity

    @property
    def total_counted(self) -> Decimal:
        return sum((value * quantity for value, quantity in self.denominations.items()), Decimal("0"))

    def confirm(self) -> None:
        if self.status is not BlindCountStatus.OPEN:
            raise CashInvalidStateError("Blind count is not open")
        self.status, self.confirmed_at = BlindCountStatus.CONFIRMED, _now()


@dataclass(frozen=True, slots=True)
class XCut:
    id: str
    shift_id: str
    branch_id: str
    generated_by: str
    expected_cash: Decimal
    operation_id: str
    document_number: str = ""
    snapshot: dict[str, str] = field(default_factory=dict)
    final: bool = False
    generated_at: str = field(default_factory=_now)

    @classmethod
    def generate(cls, *, shift_id: str, branch_id: str, generated_by: str,
                 expected_cash: Decimal, operation_id: str,
                 snapshot: dict[str, str] | None = None) -> "XCut":
        _ids(shift_id, branch_id, generated_by, operation_id)
        cut_id = new_uuid()
        number = f"X-{cut_id[:8].upper()}"
        return cls(cut_id, shift_id, branch_id, generated_by,
                   money(expected_cash), operation_id, number, dict(snapshot or {}))


@dataclass(frozen=True, slots=True)
class ZCut:
    id: str
    shift_id: str
    branch_id: str
    generated_by: str
    expected_cash: Decimal
    counted_cash: Decimal
    difference: Decimal
    blind_count_id: str
    operation_id: str
    document_number: str = ""
    snapshot: dict[str, str] = field(default_factory=dict)
    final: bool = True
    generated_at: str = field(default_factory=_now)

    @classmethod
    def generate(cls, *, shift_id: str, branch_id: str, generated_by: str,
                 expected_cash: Decimal, counted_cash: Decimal,
                 blind_count_id: str, operation_id: str,
                 snapshot: dict[str, str] | None = None) -> "ZCut":
        _ids(shift_id, branch_id, generated_by, blind_count_id, operation_id)
        expected, counted = money(expected_cash), money(counted_cash)
        cut_id = new_uuid()
        return cls(cut_id, shift_id, branch_id, generated_by, expected,
                   counted, counted - expected, blind_count_id, operation_id,
                   f"Z-{cut_id[:8].upper()}", dict(snapshot or {}))


@dataclass(slots=True)
class CashDifference:
    id: str
    shift_id: str
    z_cut_id: str
    branch_id: str
    expected_amount: Decimal
    counted_amount: Decimal
    amount: Decimal
    detected_by: str
    operation_id: str
    responsible_user_id: str = ""
    classification: CashDifferenceClassification = CashDifferenceClassification.SHORTAGE
    severity: CashDifferenceSeverity = CashDifferenceSeverity.REVIEW
    tolerance_amount: Decimal = Decimal("0")
    recurrence_count: int = 1
    status: CashDifferenceStatus = CashDifferenceStatus.DETECTED
    explanation: str | None = None
    explained_by: str | None = None
    reviewed_by: str | None = None
    resolution: str | None = None
    resolved_by: str | None = None

    @classmethod
    def detect(cls, *, shift_id: str, z_cut_id: str, branch_id: str,
               expected_amount: Decimal, counted_amount: Decimal,
               detected_by: str, operation_id: str,
               responsible_user_id: str | None = None,
               classification: CashDifferenceClassification | None = None,
               severity: CashDifferenceSeverity = CashDifferenceSeverity.REVIEW,
               tolerance_amount: Decimal = Decimal("0"),
               recurrence_count: int = 1) -> "CashDifference":
        _ids(shift_id, z_cut_id, branch_id, detected_by, operation_id)
        expected, counted = money(expected_amount), money(counted_amount)
        amount = counted - expected
        responsible = responsible_user_id or detected_by
        _ids(responsible)
        kind = classification or (CashDifferenceClassification.SHORTAGE
                                  if amount < 0 else CashDifferenceClassification.OVERAGE)
        return cls(new_uuid(), shift_id, z_cut_id, branch_id, expected, counted,
                   amount, detected_by, operation_id, responsible, kind, severity,
                   money(tolerance_amount), recurrence_count)

    def explain(self, explanation: str, actor_user_id: str) -> None:
        _ids(actor_user_id)
        if self.status is not CashDifferenceStatus.DETECTED or not explanation.strip():
            raise CashInvalidStateError("Detected difference requires an explanation")
        self.explanation, self.explained_by = explanation.strip(), actor_user_id
        self.status = CashDifferenceStatus.EXPLAINED

    def review(self, reviewer_user_id: str) -> None:
        _ids(reviewer_user_id)
        if reviewer_user_id in {self.detected_by, self.explained_by}:
            raise CashSegregationOfDutiesError("Difference review requires an independent user")
        if self.status is not CashDifferenceStatus.EXPLAINED:
            raise CashInvalidStateError("Only an explained difference can be reviewed")
        self.reviewed_by, self.status = reviewer_user_id, CashDifferenceStatus.UNDER_REVIEW

    def resolve(self, resolution: str, resolver_user_id: str) -> None:
        _ids(resolver_user_id)
        if resolver_user_id in {self.detected_by, self.explained_by, self.reviewed_by}:
            raise CashSegregationOfDutiesError("Difference resolution requires an independent user")
        if self.status is not CashDifferenceStatus.UNDER_REVIEW or not resolution.strip():
            raise CashInvalidStateError("Reviewed difference requires a resolution")
        self.resolution, self.resolved_by = resolution.strip(), resolver_user_id
        self.status = CashDifferenceStatus.RESOLVED


@dataclass(slots=True)
class CashHandover:
    id: str
    shift_id: str
    branch_id: str
    amount: Decimal
    prepared_by: str
    operation_id: str
    source_entry_id: str
    status: CashHandoverStatus = CashHandoverStatus.PREPARED
    delivered_by: str | None = None
    received_by: str | None = None
    prepared_at: str = field(default_factory=_now)
    delivered_at: str | None = None
    received_at: str | None = None

    @classmethod
    def prepare(cls, *, shift_id: str, branch_id: str, amount: Decimal,
                prepared_by: str, operation_id: str,
                source_entry_id: str | None = None) -> "CashHandover":
        source_entry_id = source_entry_id or new_uuid()
        _ids(shift_id, branch_id, prepared_by, operation_id, source_entry_id)
        return cls(new_uuid(), shift_id, branch_id, money(amount, allow_zero=False),
                   prepared_by, operation_id, source_entry_id)

    def deliver(self, delivered_by: str) -> None:
        _ids(delivered_by)
        if self.status is not CashHandoverStatus.PREPARED:
            raise CashInvalidStateError("Only a prepared handover can be delivered")
        self.delivered_by, self.status = delivered_by, CashHandoverStatus.DELIVERED
        self.delivered_at = _now()

    def receive(self, received_by: str) -> None:
        _ids(received_by)
        if self.status is not CashHandoverStatus.DELIVERED:
            raise CashInvalidStateError("Only a delivered handover can be received")
        if received_by == self.delivered_by:
            raise CashSegregationOfDutiesError("Handover receiver must differ from deliverer")
        self.received_by, self.status = received_by, CashHandoverStatus.RECEIVED
        self.received_at = _now()
