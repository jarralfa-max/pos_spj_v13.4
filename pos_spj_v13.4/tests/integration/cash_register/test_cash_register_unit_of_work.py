from decimal import Decimal
import importlib
import json
import sqlite3
import unittest

from backend.domain.cash_register.entities import (
    BlindCashCount, CashDifference, CashDrawer, CashHandover, CashLedgerEntry,
    CashRegister, CashShift, PosTerminal, ZCut,
)
from backend.domain.cash_register.enums import CashMovementDirection, CashMovementType
from backend.domain.cash_register.events import CashEvents, cash_event_payload
from backend.infrastructure.db.repositories.cash_register.unit_of_work import CashRegisterUnitOfWork
from backend.shared.ids import new_uuid


def uid():
    return new_uuid()


class CashRegisterUnitOfWorkTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        importlib.import_module(
            "migrations.standalone.175_cash_register_bounded_context_schema"
        ).run(self.db)
        importlib.import_module(
            "migrations.standalone.176_cash_register_configuration_schema"
        ).run(self.db)

    def tearDown(self):
        self.db.close()

    def _write_complete_close(self, uow):
        branch, shift_id, user = uid(), uid(), uid()
        register_id, drawer_id, terminal_id = uid(), uid(), uid()
        now = "2026-08-03T00:00:00+00:00"
        self.db.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                        (register_id, branch, "Caja test", "ACTIVE", None, now, now))
        self.db.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                        (drawer_id, branch, register_id, "Cajón test", "ACTIVE", now, now))
        self.db.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                        (terminal_id, branch, register_id, "POS test", "ACTIVE", now, now))
        shift = CashShift.open(branch_id=branch, register_id=register_id, drawer_id=drawer_id,
                               terminal_id=terminal_id, cashier_user_id=user,
                               opening_amount=Decimal("500"), operation_id=uid())
        shift.id = shift_id
        movement = CashLedgerEntry.create(
            shift_id=shift.id, branch_id=branch, movement_type=CashMovementType.OPENING_FLOAT,
            direction=CashMovementDirection.INFLOW, amount=Decimal("500"),
            operation_id=uid(), recorded_by=user)
        count = BlindCashCount.start(shift_id=shift.id, branch_id=branch,
                                     counter_user_id=user, operation_id=uid())
        count.capture(denomination=Decimal("500"), quantity=1)
        count.confirm()
        cut = ZCut.generate(shift_id=shift.id, branch_id=branch, generated_by=user,
                            expected_cash=Decimal("500"), counted_cash=Decimal("490"),
                            blind_count_id=count.id, operation_id=uid())
        difference = CashDifference.detect(
            shift_id=shift.id, z_cut_id=cut.id, branch_id=branch,
            expected_amount=cut.expected_cash, counted_amount=cut.counted_cash,
            detected_by=user, operation_id=uid())
        event = cash_event_payload(CashEvents.Z_CUT_GENERATED, operation_id=cut.operation_id,
                                   entity_id=cut.id, branch_id=branch, user_id=user,
                                   difference=str(cut.difference))
        uow.shifts.add(shift)
        uow.ledger.add(movement)
        uow.counts.add(count)
        uow.cuts.add(cut)
        uow.differences.add(difference)
        uow.events.add(event)
        uow.outbox.enqueue(event)

    def test_shift_movement_count_cut_difference_event_and_outbox_commit_together(self):
        with CashRegisterUnitOfWork(self.db) as uow:
            self._write_complete_close(uow)
        for table in ("cash_shifts", "cash_ledger_entries", "cash_counts", "cash_cuts",
                      "cash_differences", "cash_domain_events", "cash_outbox"):
            self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 1)

    def test_any_failure_rolls_back_all_cash_register_writes(self):
        with self.assertRaises(RuntimeError):
            with CashRegisterUnitOfWork(self.db) as uow:
                self._write_complete_close(uow)
                raise RuntimeError("forced failure before commit")
        for table in ("cash_shifts", "cash_ledger_entries", "cash_counts", "cash_cuts",
                      "cash_differences", "cash_domain_events", "cash_outbox"):
            self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

    def test_repositories_never_commit_and_duplicate_operation_is_atomic(self):
        uow = CashRegisterUnitOfWork(self.db)
        with self.assertRaises(sqlite3.IntegrityError):
            with uow:
                self._write_complete_close(uow)
                event = self.db.execute("SELECT payload_json FROM cash_outbox").fetchone()[0]
                duplicate = json.loads(event)
                uow.outbox.enqueue(duplicate)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM cash_shifts").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM cash_outbox").fetchone()[0], 0)

    def test_settlement_deposit_drawer_configuration_event_and_outbox_commit_together(self):
        branch, user, now = uid(), uid(), "2026-08-03T01:00:00+00:00"
        with CashRegisterUnitOfWork(self.db) as uow:
            register = CashRegister.create(branch_id=branch, name="Caja 2")
            drawer = CashDrawer.create(branch_id=branch, register_id=register.id, name="Cajon 2")
            terminal = PosTerminal.create(branch_id=branch, register_id=register.id, name="POS 2")
            shift = CashShift.open(branch_id=branch, register_id=register.id,
                                   drawer_id=drawer.id, terminal_id=terminal.id,
                                   cashier_user_id=user, opening_amount=Decimal("100"),
                                   operation_id=uid())
            safe_drop = CashLedgerEntry.create(
                shift_id=shift.id, branch_id=branch,
                movement_type=CashMovementType.SAFE_DROP,
                direction=CashMovementDirection.OUTFLOW,
                amount=Decimal("25"), operation_id=uid(), recorded_by=user,
                concept="Retiro a tesoreria",
            )
            handover = CashHandover.prepare(
                shift_id=shift.id, branch_id=branch, amount=Decimal("25"),
                prepared_by=user, operation_id=uid(), source_entry_id=safe_drop.id,
            )
            uow.devices.add_register(register, now=now)
            uow.devices.add_drawer(drawer, now=now)
            uow.devices.add_terminal(terminal, now=now)
            uow.shifts.add(shift)
            uow.ledger.add(safe_drop)
            uow.handovers.add(handover)
            uow.settlements.add_payment_record(
                payment_id=uid(), sale_id=uid(), shift_id=shift.id,
                branch_id=branch, amount_to_settle="100.00",
                operation_id=uid(), recorded_by=user, recorded_at=now,
            )
            uow.drawer_events.add_open_event(
                event_id=uid(), drawer_id=drawer.id, shift_id=shift.id,
                branch_id=branch, opened_by=user, reason="SAFE_DROP",
                operation_id=uid(), opened_at=now,
            )
            uow.deposit_preparations.add(
                deposit_id=uid(), handover_id=handover.id, branch_id=branch,
                amount="25.00", prepared_by=user, operation_id=uid(),
                denominations_json="{}", prepared_at=now,
            )
            uow.configuration.add_setting(
                row_id=uid(), setting_key="SAFE_DROP_THRESHOLD",
                setting_value="25.00", scope_type="SYSTEM", scope_id=None,
                effective_from=now, effective_to=None, created_by=user,
            )
            event = cash_event_payload(CashEvents.DEPOSIT_PREPARED,
                                       operation_id=uid(), entity_id=handover.id,
                                       branch_id=branch, user_id=user)
            uow.events.add(event)
            uow.outbox.enqueue(event)
        for table in ("payment_records", "drawer_open_events",
                      "cash_deposit_preparations", "cash_settings",
                      "cash_domain_events", "cash_outbox"):
            self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 1)

    def test_new_cash_repositories_rollback_with_the_unit_of_work(self):
        with self.assertRaises(RuntimeError):
            with CashRegisterUnitOfWork(self.db) as uow:
                uow.configuration.add_setting(
                    row_id=uid(), setting_key="ROLLBACK_PROBE",
                    setting_value="1", scope_type="SYSTEM", scope_id=None,
                    effective_from="2026-08-03T01:00:00+00:00",
                    effective_to=None, created_by=uid(),
                )
                raise RuntimeError("forced rollback")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM cash_settings").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
