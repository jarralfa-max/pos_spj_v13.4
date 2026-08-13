from decimal import Decimal
import unittest

from backend.domain.cash_register.entities import (
    BlindCashCount, CashDifference, CashDrawer, CashHandover, CashLedger,
    CashLedgerEntry, CashRefundExecution, CashRegister, CashShift,
    DrawerOpenEvent, PaymentRecord, PosTerminal, XCut, ZCut,
)
from backend.domain.cash_register.enums import (
    CashDifferenceStatus, CashHandoverStatus, CashMovementDirection,
    CashMovementType, CashPaymentMethodType, CashRefundMethod,
    CashShiftStatus, DeviceStatus, DrawerOpenReason,
)
from backend.domain.cash_register.events import CashEvents, cash_event_payload
from backend.domain.cash_register.exceptions import (
    CashDuplicateOperationError, CashInvalidStateError,
    CashSegregationOfDutiesError,
)
from backend.domain.cash_register.policies.workflow_policies import CashClosingPolicy
from backend.domain.cash_register.settlements import classify_settlement
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

    def test_canonical_domain_catalogs_cover_operational_states(self):
        self.assertTrue({"ACTIVE", "INACTIVE", "MAINTENANCE", "BLOCKED", "RETIRED"} <= {item.value for item in DeviceStatus})
        self.assertTrue({"OPENING", "OPEN", "SUSPENDED", "COUNTING", "CLOSING", "CLOSED", "FORCE_CLOSED"} <= {item.value for item in CashShiftStatus})
        self.assertTrue({"OPENING_FLOAT", "CASH_SALE", "CASH_REFUND", "SAFE_DROP", "CASH_HANDOVER", "REVERSAL"} <= {item.value for item in CashMovementType})
        self.assertTrue({"DRAFT", "READY", "IN_TRANSIT", "RECEIVED", "DISPUTED", "CANCELLED"} <= {item.value for item in CashHandoverStatus})

    def test_payment_record_allocations_balance_and_drawer_effect(self):
        payment = PaymentRecord.create(
            sale_id=uid(), shift_id=uid(), branch_id=uid(),
            amount_to_settle=Decimal("1000.00"), operation_id=uid(),
            recorded_by=uid(),
        )
        payment.add_allocation(method_type=CashPaymentMethodType.CASH,
                               amount=Decimal("400.00"), affects_drawer=True)
        payment.add_allocation(method_type=CashPaymentMethodType.BANK_CARD,
                               amount=Decimal("350.00"), affects_drawer=False,
                               external_reference="terminal-batch")
        payment.add_allocation(method_type=CashPaymentMethodType.BANK_TRANSFER,
                               amount=Decimal("150.00"), affects_drawer=False)
        payment.add_allocation(method_type=CashPaymentMethodType.LOYALTY_POINTS,
                               amount=Decimal("100.00"), affects_drawer=False)
        payment.confirm_balanced()
        self.assertEqual(payment.allocated_total, Decimal("1000.00"))
        self.assertEqual(payment.drawer_effect, Decimal("400.00"))
        with self.assertRaises(TypeError):
            payment.add_allocation(method_type=CashPaymentMethodType.CASH,
                                   amount=1.0, affects_drawer=True)

    def test_settlement_classifier_uses_canonical_payment_types(self):
        self.assertEqual(classify_settlement("CARD").canonical_type, "BANK_CARD")
        self.assertEqual(classify_settlement("ON_CREDIT").canonical_type, "CUSTOMER_CREDIT")
        self.assertFalse(classify_settlement("REFUND_VOUCHER").affects_drawer)
        with self.assertRaises(CashInvalidStateError):
            classify_settlement("GIFT_CARD")
        self.assertEqual(classify_settlement("GIFT_CARD", allow_future=True).canonical_type, "GIFT_CARD")

    def test_refund_execution_and_drawer_open_event_are_uuid_domain_documents(self):
        executed_by, authorized_by = uid(), uid()
        execution = CashRefundExecution.execute(
            refund_id=uid(), sale_id=uid(), shift_id=uid(), branch_id=uid(),
            method=CashRefundMethod.CASH, amount=Decimal("125.00"),
            executed_by=executed_by, authorized_by=authorized_by,
            operation_id=uid(), ledger_entry_id=uid(),
        )
        self.assertTrue(is_uuidv7(execution.id))
        self.assertEqual(execution.method, CashRefundMethod.CASH)
        with self.assertRaises(CashSegregationOfDutiesError):
            CashRefundExecution.execute(
                refund_id=uid(), sale_id=uid(), shift_id=uid(), branch_id=uid(),
                method=CashRefundMethod.CASH, amount=Decimal("1.00"),
                executed_by=executed_by, authorized_by=executed_by,
                operation_id=uid(),
            )
        drawer_event = DrawerOpenEvent.record(
            drawer_id=uid(), shift_id=uid(), branch_id=uid(),
            opened_by=uid(), reason=DrawerOpenReason.NO_SALE_AUTHORIZED,
            operation_id=uid(), source_document_id=uid(),
        )
        self.assertTrue(is_uuidv7(drawer_event.id))
        self.assertEqual(drawer_event.reason, DrawerOpenReason.NO_SALE_AUTHORIZED)


if __name__ == "__main__":
    unittest.main()
