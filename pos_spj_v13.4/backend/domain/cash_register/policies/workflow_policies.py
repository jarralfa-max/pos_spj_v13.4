"""Cross-aggregate pure workflow policies for Cash Register."""
from __future__ import annotations

from typing import TYPE_CHECKING

from backend.domain.cash_register.enums import BlindCountStatus, CashShiftStatus
from backend.domain.cash_register.exceptions import CashDuplicateOperationError, CashInvalidStateError

if TYPE_CHECKING:
    from backend.domain.cash_register.entities import BlindCashCount, CashShift


class CashShiftLifecyclePolicy:
    """Canonical lifecycle invariants for CashShift.

    This policy is intentionally enum-based so application services can validate
    rows from repositories without recreating a domain entity, while the
    aggregate can reuse exactly the same transition table.
    """

    ACTIVE_STATUSES = frozenset({
        CashShiftStatus.OPENING,
        CashShiftStatus.OPEN,
        CashShiftStatus.SUSPENDED,
        CashShiftStatus.PENDING_COUNT,
        CashShiftStatus.COUNTING,
        CashShiftStatus.COUNTED,
        CashShiftStatus.PENDING_REVIEW,
        CashShiftStatus.CLOSING,
    })
    FINAL_STATUSES = frozenset({
        CashShiftStatus.CLOSED,
        CashShiftStatus.FORCE_CLOSED,
        CashShiftStatus.CANCELLED,
    })
    TRANSITIONS = {
        (CashShiftStatus.OPEN, CashShiftStatus.SUSPENDED),
        (CashShiftStatus.SUSPENDED, CashShiftStatus.OPEN),
        (CashShiftStatus.OPEN, CashShiftStatus.CLOSING),
        (CashShiftStatus.CLOSING, CashShiftStatus.CLOSED),
    }

    @classmethod
    def normalize(cls, status: CashShiftStatus | str) -> CashShiftStatus:
        if isinstance(status, CashShiftStatus):
            return status
        try:
            return CashShiftStatus(str(status))
        except ValueError as exc:
            raise CashInvalidStateError(f"Unknown cash shift status: {status}") from exc

    @classmethod
    def is_active(cls, status: CashShiftStatus | str) -> bool:
        return cls.normalize(status) in cls.ACTIVE_STATUSES

    @classmethod
    def ensure_operable(cls, status: CashShiftStatus | str) -> None:
        if cls.normalize(status) is not CashShiftStatus.OPEN:
            raise CashInvalidStateError("Cash operation requires an OPEN shift")

    @classmethod
    def ensure_transition(
        cls,
        *,
        current: CashShiftStatus | str,
        target: CashShiftStatus | str,
        reason: str = "",
        has_final_z_cut: bool = False,
    ) -> None:
        current_status = cls.normalize(current)
        target_status = cls.normalize(target)
        if current_status in cls.FINAL_STATUSES:
            raise CashInvalidStateError("Final cash shifts cannot transition")
        if (current_status, target_status) not in cls.TRANSITIONS:
            raise CashInvalidStateError(
                f"Invalid cash shift transition: {current_status.value} -> {target_status.value}"
            )
        if target_status is CashShiftStatus.SUSPENDED and not reason.strip():
            raise CashInvalidStateError("Shift suspension requires an operational reason")
        if target_status is CashShiftStatus.CLOSED and not has_final_z_cut:
            raise CashInvalidStateError("Shift closure requires one final Z cut")


class CashClosingPolicy:
    def ensure_ready_for_z_cut(self, *, shift: CashShift,
                               blind_count: BlindCashCount,
                               has_pending_operations: bool) -> None:
        if shift.status is not CashShiftStatus.CLOSING:
            raise CashInvalidStateError("Z cut requires a shift in CLOSING state")
        if blind_count.shift_id != shift.id or blind_count.status is not BlindCountStatus.CONFIRMED:
            raise CashInvalidStateError("Z cut requires the confirmed blind count of this shift")
        if has_pending_operations:
            raise CashInvalidStateError("Z cut cannot run with pending operations")

    @staticmethod
    def ensure_single_final_z_cut(*, existing_z_cut_id: str | None) -> None:
        if existing_z_cut_id:
            raise CashDuplicateOperationError("The shift already has a final Z cut")


class CashDeviceAvailabilityPolicy:
    @staticmethod
    def ensure_shift_devices_available(*, register_status, drawer_status,
                                       terminal_status) -> None:
        statuses = (register_status, drawer_status, terminal_status)
        if any(getattr(status, "value", status) != "ACTIVE" for status in statuses):
            raise CashInvalidStateError("Register, drawer and terminal must be active")
