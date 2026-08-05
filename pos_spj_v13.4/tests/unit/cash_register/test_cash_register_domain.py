from decimal import Decimal
import unittest

from backend.domain.cash_register.entities import (
    BlindCashCount, CashDifference, CashDrawer, CashHandover, CashLedger,
    CashLedgerEntry, CashRegister, CashShift, PosTerminal, XCut, ZCut,
)
from backend.domain.cash_register.enums import (
    CashDifferenceStatus, CashHandoverStatus, CashMovementDirection,
    CashMovementType, CashShiftStatus, DeviceStatus,
)
from backend.domain.cash_register.events import CashEvents, cash_event_payload
from backend.domain.cash_register.exceptions import (
    CashDuplicateOperationError, CashInvalidStateError,
    CashSegregationOfDutiesError,
)
from backend.domain.cash_register.policies.workflow_policies import CashClosingPolicy
from backend.shared.ids import is_uuidv7, new_uuid


def uid():
    return new_uuid()


class CashRegisterDomainTests(unittest.TestCase):
    def test_register_drawer_and_terminal_use_separate_uuid_identities(self):
        branch_id = uid()
        register = CashRegister.create(branch_id=branch_id, name="Caja 1")
        drawer = CashDrawer.create(branch_id=branch_id, register_id=register.id, name="Cajón A")
        terminal = PosTerminal.create(branch_id=branch_id, register_id=register.id, name="POS A")
        self.assertTrue(all(is_uuidv7(value) for value in (register.id, drawer.id, terminal.id)))
        self.assertEqual(len({register.id, drawer.id, terminal.id}), 3)
        register.block("mantenimiento")
        self.assertIs(register.status, DeviceStatus.BLOCKED)

    def test_shift_workflow_and_single_open_identity(self):
        shift = CashShift.open(branch_id=uid(), register_id=uid(), drawer_id=uid(),
                               terminal_id=uid(), cashier_user_id=uid(),
                               opening_amount=Decimal("500.00"), operation_id=uid())
        self.assertIs(shift.status, CashShiftStatus.OPEN)
        shift.suspend("pausa")
        shift.resume()
        shift.begin_closing()
        shift.close(z_cut_id=uid())
        self.assertIs(shift.status, CashShiftStatus.CLOSED)
        with self.assertRaises(CashInvalidStateError):
            shift.close(z_cut_id=uid())

    def test_ledger_is_reconstructible_decimal_and_idempotent(self):
        shift_id, branch_id = uid(), uid()
        ledger = CashLedger(shift_id=shift_id)
        opening = CashLedgerEntry.create(
            shift_id=shift_id, branch_id=branch_id, movement_type=CashMovementType.OPENING_FLOAT,
            direction=CashMovementDirection.INFLOW, amount=Decimal("500"),
            operation_id=uid(), recorded_by=uid())
        sale = CashLedgerEntry.create(
            shift_id=shift_id, branch_id=branch_id, movement_type=CashMovementType.CASH_SALE,
            direction=CashMovementDirection.INFLOW, amount=Decimal("125.50"),
            operation_id=uid(), recorded_by=uid())
        drop = CashLedgerEntry.create(
            shift_id=shift_id, branch_id=branch_id, movement_type=CashMovementType.SAFE_DROP,
            direction=CashMovementDirection.OUTFLOW, amount=Decimal("100"),
            operation_id=uid(), recorded_by=uid())
        for entry in (opening, sale, drop):
            ledger.append(entry)
        self.assertEqual(ledger.balance, Decimal("525.50"))
        with self.assertRaises(CashDuplicateOperationError):
            ledger.append(opening)
        with self.assertRaises(TypeError):
            CashLedgerEntry.create(shift_id=shift_id, branch_id=branch_id,
                movement_type=CashMovementType.CASH_SALE, direction=CashMovementDirection.INFLOW,
                amount=1.5, operation_id=uid(), recorded_by=uid())

    def test_blind_count_has_no_expected_amount_and_locks_after_confirmation(self):
        count = BlindCashCount.start(shift_id=uid(), branch_id=uid(), counter_user_id=uid(),
                                     operation_id=uid())
        count.capture(denomination=Decimal("200"), quantity=2)
        count.capture(denomination=Decimal("50"), quantity=1)
        self.assertEqual(count.total_counted, Decimal("450"))
        self.assertFalse(hasattr(count, "expected_amount"))
        count.confirm()
        with self.assertRaises(CashInvalidStateError):
            count.capture(denomination=Decimal("20"), quantity=1)

    def test_x_cut_does_not_close_shift_and_z_cut_is_final(self):
        shift = CashShift.open(branch_id=uid(), register_id=uid(), drawer_id=uid(),
                               terminal_id=uid(), cashier_user_id=uid(),
                               opening_amount=Decimal("0"), operation_id=uid())
        x_cut = XCut.generate(shift_id=shift.id, branch_id=shift.branch_id,
                              generated_by=uid(), expected_cash=Decimal("100"),
                              operation_id=uid())
        self.assertIs(shift.status, CashShiftStatus.OPEN)
        self.assertFalse(x_cut.final)
        z_cut = ZCut.generate(shift_id=shift.id, branch_id=shift.branch_id,
                              generated_by=uid(), expected_cash=Decimal("100"),
                              counted_cash=Decimal("95"), blind_count_id=uid(),
                              operation_id=uid())
        self.assertTrue(z_cut.final)
        self.assertEqual(z_cut.difference, Decimal("-5"))
        CashClosingPolicy().ensure_single_final_z_cut(existing_z_cut_id=None)
        with self.assertRaises(CashDuplicateOperationError):
            CashClosingPolicy().ensure_single_final_z_cut(existing_z_cut_id=z_cut.id)

    def test_difference_and_handover_enforce_independent_users(self):
        counter, reviewer = uid(), uid()
        difference = CashDifference.detect(
            shift_id=uid(), z_cut_id=uid(), branch_id=uid(),
            expected_amount=Decimal("100"), counted_amount=Decimal("90"),
            detected_by=counter, operation_id=uid())
        difference.explain("Falta pendiente de investigación", counter)
        with self.assertRaises(CashSegregationOfDutiesError):
            difference.review(counter)
        difference.review(reviewer)
        difference.resolve("Ajuste autorizado", uid())
        self.assertIs(difference.status, CashDifferenceStatus.RESOLVED)

        delivered_by, received_by = uid(), uid()
        handover = CashHandover.prepare(shift_id=uid(), branch_id=uid(),
                                        amount=Decimal("1000"), prepared_by=delivered_by,
                                        operation_id=uid())
        handover.deliver(delivered_by)
        with self.assertRaises(CashSegregationOfDutiesError):
            handover.receive(delivered_by)
        handover.receive(received_by)
        self.assertIs(handover.status, CashHandoverStatus.RECEIVED)

    def test_events_have_distinct_uuid_contract(self):
        operation_id, entity_id, branch_id, user_id = uid(), uid(), uid(), uid()
        event = cash_event_payload(CashEvents.SHIFT_OPENED, operation_id=operation_id,
                                   entity_id=entity_id, branch_id=branch_id, user_id=user_id)
        self.assertTrue(is_uuidv7(event["event_id"]))
        self.assertEqual(event["source_module"], "cash_register")
        self.assertEqual(len({event["event_id"], operation_id, entity_id}), 3)
        with self.assertRaises(ValueError):
            cash_event_payload("CAJA_ABIERTA", operation_id=operation_id,
                               entity_id=entity_id, branch_id=branch_id, user_id=user_id)


if __name__ == "__main__":
    unittest.main()
