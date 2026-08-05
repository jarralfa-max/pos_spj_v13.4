"""Cross-aggregate pure workflow policies for Cash Register."""
from backend.domain.cash_register.entities import BlindCashCount, CashShift
from backend.domain.cash_register.enums import BlindCountStatus, CashShiftStatus
from backend.domain.cash_register.exceptions import CashDuplicateOperationError, CashInvalidStateError


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
