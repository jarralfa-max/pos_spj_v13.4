"""DB-API repositories for the canonical Cash Register schema.

Repositories deliberately never commit or roll back. CashRegisterUnitOfWork is
the sole transaction owner.
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from backend.domain.cash_register.entities import (
    BlindCashCount, CashDifference, CashDrawer, CashHandover, CashLedgerEntry,
    CashRegister, CashShift, PosTerminal, XCut, ZCut,
)
from backend.shared.ids import new_uuid


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class _Repository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def execute(self, sql: str, params: tuple = ()):
        return self.connection.execute(sql, params)


class CashShiftRepository(_Repository):
    def add(self, shift: CashShift) -> None:
        self.execute(
            """INSERT INTO cash_shifts
            (id,branch_id,register_id,drawer_id,terminal_id,cashier_user_id,
             opening_amount,opening_operation_id,status,opened_at,z_cut_id,closed_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (shift.id, shift.branch_id, shift.register_id, shift.drawer_id,
             shift.terminal_id, shift.cashier_user_id, str(shift.opening_amount),
             shift.opening_operation_id, shift.status.value, shift.opened_at,
             shift.z_cut_id, shift.closed_at))

    def get(self, shift_id: str):
        cursor = self.execute("SELECT * FROM cash_shifts WHERE id=?", (shift_id,))
        row = cursor.fetchone()
        if row is None: return None
        columns = [item[0] for item in cursor.description]
        return dict(zip(columns, row))

    def set_lifecycle(self, *, shift_id: str, status: str,
                      suspended_reason: str | None = None) -> None:
        self.execute("UPDATE cash_shifts SET status=?,suspended_reason=? WHERE id=?",
                     (status, suspended_reason, shift_id))

    def find_open_for_cashier(self, *, branch_id: str, cashier_user_id: str):
        cursor = self.execute(
            "SELECT * FROM cash_shifts WHERE branch_id=? AND cashier_user_id=? AND status='OPEN'",
            (branch_id, cashier_user_id))
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(zip((item[0] for item in cursor.description), row))

    def close(self, *, shift_id: str, z_cut_id: str, closed_at: str) -> None:
        cursor = self.execute(
            """UPDATE cash_shifts SET status='CLOSED',z_cut_id=?,closed_at=?
            WHERE id=? AND status='CLOSING' AND z_cut_id IS NULL""",
            (z_cut_id, closed_at, shift_id))
        if cursor.rowcount != 1:
            raise RuntimeError("Shift is not ready for final closure")


class CashDeviceRepository(_Repository):
    _TABLES = {"register": "cash_registers", "drawer": "cash_drawers", "terminal": "pos_terminals"}

    def add_register(self, device: CashRegister, *, now: str) -> None:
        self.execute("INSERT INTO cash_registers(id,branch_id,name,status,blocked_reason,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                     (device.id, device.branch_id, device.name, device.status.value,
                      device.blocked_reason, now, now))

    def add_drawer(self, device: CashDrawer, *, now: str) -> None:
        self.execute("INSERT INTO cash_drawers(id,branch_id,register_id,name,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                     (device.id, device.branch_id, device.register_id, device.name,
                      device.status.value, now, now))

    def add_terminal(self, device: PosTerminal, *, now: str) -> None:
        self.execute("INSERT INTO pos_terminals(id,branch_id,register_id,name,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                     (device.id, device.branch_id, device.register_id, device.name,
                      device.status.value, now, now))

    def get(self, kind: str, device_id: str):
        table = self._TABLES[kind]
        cursor = self.execute(f"SELECT * FROM {table} WHERE id=?", (device_id,))
        row = cursor.fetchone()
        if row is None: return None
        columns = [item[0] for item in cursor.description]
        return dict(zip(columns, row))

    def set_status(self, kind: str, device_id: str, status: str, *, reason: str | None, now: str) -> None:
        table = self._TABLES[kind]
        if kind == "register":
            self.execute(f"UPDATE {table} SET status=?,blocked_reason=?,updated_at=? WHERE id=?",
                         (status, reason, now, device_id))
        else:
            self.execute(f"UPDATE {table} SET status=?,updated_at=? WHERE id=?", (status, now, device_id))

    def assign(self, kind: str, device_id: str, register_id: str, *, now: str) -> None:
        if kind not in {"drawer", "terminal"}: raise ValueError("Only drawers and terminals are assignable")
        self.execute(f"UPDATE {self._TABLES[kind]} SET register_id=?,updated_at=? WHERE id=?",
                     (register_id, now, device_id))

    def list_devices(self, kind: str) -> list[dict]:
        table = self._TABLES[kind]
        assignment = "''" if kind == "register" else "register_id"
        cursor = self.execute(
            f"SELECT id,name,branch_id branch_name,{assignment} assignment,status,'No verificado' hardware_status FROM {table} ORDER BY name")
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


class CashAuditRepository(_Repository):
    def record(self, *, audit_id: str, action: str, actor_user_id: str,
               entity_id: str, branch_id: str, operation_id: str,
               reason: str, occurred_at: str) -> None:
        self.execute("""INSERT INTO cash_audit_log
            (id,action,actor_user_id,entity_id,branch_id,operation_id,reason,occurred_at)
            VALUES(?,?,?,?,?,?,?,?)""",
            (audit_id, action, actor_user_id, entity_id, branch_id,
             operation_id, reason, occurred_at))


class CashLedgerRepository(_Repository):
    def add(self, entry: CashLedgerEntry) -> None:
        self.execute(
            """INSERT INTO cash_ledger_entries
            (id,shift_id,branch_id,movement_type,direction,amount,operation_id,
             recorded_by,concept,reference_id,reversal_of_id,related_sale_id,recorded_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (entry.id, entry.shift_id, entry.branch_id, entry.movement_type.value,
             entry.direction.value, str(entry.amount), entry.operation_id,
             entry.recorded_by, entry.concept, entry.reference_id, entry.reversal_of_id,
             entry.related_sale_id,
             entry.recorded_at))

    def get(self, entry_id: str):
        return self._one("SELECT * FROM cash_ledger_entries WHERE id=?", (entry_id,))

    def get_by_operation(self, operation_id: str):
        return self._one("SELECT * FROM cash_ledger_entries WHERE operation_id=?", (operation_id,))

    def find_reversal(self, original_id: str):
        return self._one("SELECT * FROM cash_ledger_entries WHERE reversal_of_id=?", (original_id,))

    def find_sale_entry(self, sale_id: str):
        return self._one(
            "SELECT * FROM cash_ledger_entries WHERE reference_id=? AND movement_type='CASH_SALE'",
            (sale_id,))

    def find_refund_entry(self, refund_id: str):
        return self._one(
            "SELECT * FROM cash_ledger_entries WHERE reference_id=? AND movement_type='CASH_REFUND'",
            (refund_id,))

    def refunded_cash_for_sale(self, sale_id: str) -> Decimal:
        rows = self.execute(
            "SELECT amount FROM cash_ledger_entries WHERE related_sale_id=? AND movement_type='CASH_REFUND'",
            (sale_id,)).fetchall()
        return sum((Decimal(row[0]) for row in rows), Decimal("0"))

    def list_for_shift(self, shift_id: str) -> list[dict]:
        cursor = self.execute(
            "SELECT * FROM cash_ledger_entries WHERE shift_id=? ORDER BY recorded_at,id",
            (shift_id,))
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _one(self, sql: str, params: tuple):
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(zip((item[0] for item in cursor.description), row))


class CashSettlementRepository(_Repository):
    """Canonical settlement persistence owned by Caja, not Ventas."""

    def add_payment_record(self, *, payment_id: str, sale_id: str,
                           shift_id: str, branch_id: str,
                           amount_to_settle: str, operation_id: str,
                           recorded_by: str, recorded_at: str,
                           status: str = "CONFIRMED") -> None:
        self.execute(
            """INSERT INTO payment_records
            (id,sale_id,shift_id,branch_id,amount_to_settle,operation_id,
             recorded_by,recorded_at,status)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (payment_id, sale_id, shift_id, branch_id, amount_to_settle,
             operation_id, recorded_by, recorded_at, status),
        )

    def add_payment_allocation(self, *, allocation_id: str,
                               payment_record_id: str, method_type: str,
                               amount: str, affects_drawer: bool,
                               created_at: str,
                               external_reference: str | None = None) -> None:
        self.execute(
            """INSERT INTO payment_allocations
            (id,payment_record_id,method_type,amount,affects_drawer,
             external_reference,created_at)
            VALUES(?,?,?,?,?,?,?)""",
            (allocation_id, payment_record_id, method_type, amount,
             1 if affects_drawer else 0, external_reference, created_at),
        )

    def add_refund_execution(self, *, execution_id: str, refund_id: str,
                             sale_id: str, shift_id: str, branch_id: str,
                             method: str, amount: str, executed_by: str,
                             authorized_by: str, operation_id: str,
                             executed_at: str,
                             ledger_entry_id: str | None = None) -> None:
        self.execute(
            """INSERT INTO cash_refund_executions
            (id,refund_id,sale_id,shift_id,branch_id,method,amount,
             executed_by,authorized_by,operation_id,ledger_entry_id,executed_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (execution_id, refund_id, sale_id, shift_id, branch_id, method,
             amount, executed_by, authorized_by, operation_id, ledger_entry_id,
             executed_at),
        )


class CashDrawerEventRepository(_Repository):
    def add_open_event(self, *, event_id: str, drawer_id: str, shift_id: str,
                       branch_id: str, opened_by: str, reason: str,
                       operation_id: str, opened_at: str,
                       source_document_id: str | None = None) -> None:
        self.execute(
            """INSERT INTO drawer_open_events
            (id,drawer_id,shift_id,branch_id,opened_by,reason,operation_id,
             source_document_id,opened_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (event_id, drawer_id, shift_id, branch_id, opened_by, reason,
             operation_id, source_document_id, opened_at),
        )


class CashDepositPreparationRepository(_Repository):
    def add(self, *, deposit_id: str, handover_id: str, branch_id: str,
            amount: str, prepared_by: str, operation_id: str,
            denominations_json: str, prepared_at: str,
            status: str = "PREPARED") -> None:
        self.execute(
            """INSERT INTO cash_deposit_preparations
            (id,handover_id,branch_id,amount,prepared_by,operation_id,status,
             denominations_json,prepared_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (deposit_id, handover_id, branch_id, amount, prepared_by,
             operation_id, status, denominations_json, prepared_at),
        )


class CashMovementReasonRepository(_Repository):
    def list_active(self, *, movement_type: str, occurred_at: str) -> list[dict]:
        cursor = self.execute(
            """SELECT code,display_name,movement_type,requires_authorization
            FROM cash_movement_reasons
            WHERE movement_type=? AND active=1
              AND effective_from<=?
              AND (effective_to IS NULL OR effective_to>?)
            ORDER BY display_name,code""",
            (movement_type.strip().upper(), occurred_at, occurred_at))
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_active(self, *, code: str, movement_type: str, occurred_at: str):
        cursor = self.execute(
            """SELECT * FROM cash_movement_reasons
            WHERE code=? AND movement_type=? AND active=1 AND effective_from<=?
              AND (effective_to IS NULL OR effective_to>?)
            ORDER BY effective_from DESC LIMIT 1""",
            (code.strip().upper(), movement_type, occurred_at, occurred_at))
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(zip((item[0] for item in cursor.description), row))


class CashHandoverRepository(_Repository):
    def add(self, handover: CashHandover) -> None:
        self.execute(
            """INSERT INTO cash_handovers
            (id,shift_id,branch_id,amount,prepared_by,delivered_by,received_by,
             operation_id,source_entry_id,status,prepared_at,delivered_at,received_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (handover.id, handover.shift_id, handover.branch_id, str(handover.amount),
             handover.prepared_by, handover.delivered_by, handover.received_by,
             handover.operation_id, handover.source_entry_id, handover.status.value,
             handover.prepared_at, handover.delivered_at, handover.received_at))

    def get(self, handover_id: str):
        cursor = self.execute("SELECT * FROM cash_handovers WHERE id=?", (handover_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(zip((item[0] for item in cursor.description), row))

    def get_by_operation(self, operation_id: str):
        cursor = self.execute("SELECT * FROM cash_handovers WHERE operation_id=?", (operation_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(zip((item[0] for item in cursor.description), row))

    def list_for_branch(self, *, branch_id: str, limit: int = 100) -> list[dict]:
        cursor = self.execute(
            """SELECT id,shift_id,branch_id,amount,prepared_by,delivered_by,received_by,
            source_entry_id,status,prepared_at,delivered_at,received_at,disputed_by,
            disputed_at,dispute_reason FROM cash_handovers
            WHERE branch_id=?
            ORDER BY prepared_at DESC,id DESC LIMIT ?""",
            (branch_id, int(limit)),
        )
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def transition(self, *, handover_id: str, source_status: str, target_status: str,
                   actor_column: str, actor_user_id: str, timestamp_column: str,
                   timestamp: str) -> None:
        if actor_column not in {"delivered_by", "received_by"} or timestamp_column not in {
            "delivered_at", "received_at"
        }:
            raise ValueError("Invalid handover transition columns")
        cursor = self.execute(
            f"UPDATE cash_handovers SET status=?,{actor_column}=?,{timestamp_column}=? WHERE id=? AND status=?",
            (target_status, actor_user_id, timestamp, handover_id, source_status))
        if cursor.rowcount != 1:
            raise RuntimeError("Concurrent or invalid handover transition")

    def unresolved_safe_drop_count(self, shift_id: str) -> int:
        return int(self.execute(
            """SELECT COUNT(*) FROM cash_ledger_entries l
            LEFT JOIN cash_handovers h ON h.source_entry_id=l.id
            WHERE l.shift_id=? AND l.movement_type='SAFE_DROP'
              AND (h.id IS NULL OR h.status<>'RECEIVED')""", (shift_id,)).fetchone()[0])

    def add_denominations(self, handover_id: str, lines: list[dict]) -> None:
        for line in lines:
            self.execute(
                """INSERT INTO cash_handover_denominations
                (id,handover_id,denomination_id,denomination,quantity,subtotal)
                VALUES(?,?,?,?,?,?)""",
                (line["id"], handover_id, line["denomination_id"],
                 line["denomination"], line["quantity"], line["subtotal"]))

    def list_denominations(self, handover_id: str) -> list[dict]:
        cursor = self.execute(
            "SELECT * FROM cash_handover_denominations WHERE handover_id=? ORDER BY CAST(denomination AS NUMERIC) DESC",
            (handover_id,))
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def add_confirmation(self, *, confirmation_id: str, handover_id: str,
                         confirmation_type: str, confirmed_by: str,
                         operation_id: str, denominations_json: str,
                         total_amount: str, notes: str, confirmed_at: str) -> None:
        self.execute(
            """INSERT INTO cash_handover_confirmations
            (id,handover_id,confirmation_type,confirmed_by,operation_id,
             denominations_json,total_amount,notes,confirmed_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (confirmation_id, handover_id, confirmation_type, confirmed_by,
             operation_id, denominations_json, total_amount, notes, confirmed_at))

    def get_confirmation_by_operation(self, operation_id: str):
        cursor = self.execute(
            "SELECT * FROM cash_handover_confirmations WHERE operation_id=?", (operation_id,))
        row = cursor.fetchone()
        if row is None: return None
        return dict(zip((item[0] for item in cursor.description), row))

    def dispute(self, *, handover_id: str, source_status: str,
                disputed_by: str, disputed_at: str, reason: str) -> None:
        cursor = self.execute(
            """UPDATE cash_handovers SET status='DISPUTED',disputed_by=?,disputed_at=?,dispute_reason=?
            WHERE id=? AND status=?""",
            (disputed_by, disputed_at, reason, handover_id, source_status))
        if cursor.rowcount != 1:
            raise RuntimeError("Concurrent or invalid handover dispute")


class CashCountRepository(_Repository):
    def add(self, count: BlindCashCount) -> None:
        denominations = {str(value): quantity for value, quantity in count.denominations.items()}
        self.execute(
            """INSERT INTO cash_counts
            (id,shift_id,branch_id,counter_user_id,operation_id,denominations_json,
             total_counted,status,confirmed_at) VALUES (?,?,?,?,?,?,?,?,?)""",
            (count.id, count.shift_id, count.branch_id, count.counter_user_id,
             count.operation_id, _json(denominations), str(count.total_counted),
             count.status.value, count.confirmed_at))

    def get(self, count_id: str):
        cursor = self.execute("SELECT * FROM cash_counts WHERE id=?", (count_id,))
        row = cursor.fetchone()
        if row is None: return None
        return dict(zip((item[0] for item in cursor.description), row))

    def get_by_operation(self, operation_id: str):
        cursor = self.execute("SELECT * FROM cash_counts WHERE operation_id=?", (operation_id,))
        row = cursor.fetchone()
        if row is None: return None
        return dict(zip((item[0] for item in cursor.description), row))

    def find_open_for_shift(self, shift_id: str):
        cursor = self.execute("SELECT * FROM cash_counts WHERE shift_id=? AND status='OPEN'", (shift_id,))
        row = cursor.fetchone()
        if row is None: return None
        return dict(zip((item[0] for item in cursor.description), row))

    def find_confirmed_for_final_cut(self, shift_id: str):
        cursor = self.execute(
            """SELECT c.* FROM cash_counts c LEFT JOIN cash_cuts z
            ON z.blind_count_id=c.id AND z.cut_type='Z' AND z.is_final=1
            WHERE c.shift_id=? AND c.status='CONFIRMED' AND z.id IS NULL
            ORDER BY c.confirmed_at DESC LIMIT 1""", (shift_id,))
        row = cursor.fetchone()
        if row is None: return None
        return dict(zip((item[0] for item in cursor.description), row))

    def get_active_denomination(self, denomination_id: str, *, occurred_at: str):
        cursor = self.execute(
            """SELECT * FROM cash_denominations WHERE id=? AND active=1
            AND effective_from<=? AND (effective_to IS NULL OR effective_to>?)""",
            (denomination_id, occurred_at, occurred_at))
        row = cursor.fetchone()
        if row is None: return None
        return dict(zip((item[0] for item in cursor.description), row))

    def list_active_denominations(self) -> list[dict]:
        cursor = self.execute(
            """SELECT id,display_name,denomination_value FROM cash_denominations
            WHERE active=1 ORDER BY sort_order,CAST(denomination_value AS NUMERIC) DESC""")
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def capture(self, *, count_id: str, denomination_id: str,
                denomination: str, quantity: int, row_id: str) -> None:
        count = self.get(count_id)
        if not count or count["status"] != "OPEN":
            raise RuntimeError("Blind count is locked")
        subtotal = Decimal(denomination) * quantity
        self.execute(
            """INSERT INTO cash_count_denominations
            (id,count_id,denomination_id,denomination,quantity,subtotal)
            VALUES(?,?,?,?,?,?) ON CONFLICT(count_id,denomination_id)
            DO UPDATE SET quantity=excluded.quantity,subtotal=excluded.subtotal""",
            (row_id, count_id, denomination_id, denomination, quantity, str(subtotal)))
        rows = self.list_denominations(count_id)
        total = sum((Decimal(item["subtotal"]) for item in rows), Decimal("0"))
        payload = {item["denomination"]: item["quantity"] for item in rows}
        cursor = self.execute(
            "UPDATE cash_counts SET denominations_json=?,total_counted=? WHERE id=? AND status='OPEN'",
            (_json(payload), str(total), count_id))
        if cursor.rowcount != 1: raise RuntimeError("Blind count was locked concurrently")

    def list_denominations(self, count_id: str) -> list[dict]:
        cursor = self.execute(
            "SELECT * FROM cash_count_denominations WHERE count_id=? ORDER BY CAST(denomination AS NUMERIC) DESC",
            (count_id,))
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def confirm(self, *, count_id: str, confirmed_at: str) -> None:
        cursor = self.execute(
            "UPDATE cash_counts SET status='CONFIRMED',confirmed_at=? WHERE id=? AND status='OPEN'",
            (confirmed_at, count_id))
        if cursor.rowcount != 1: raise RuntimeError("Blind count is already locked")


class CashIdempotencyRepository(_Repository):
    def get(self, operation_id: str):
        cursor = self.execute("SELECT * FROM cash_processed_operations WHERE operation_id=?", (operation_id,))
        row = cursor.fetchone()
        if row is None: return None
        return dict(zip((item[0] for item in cursor.description), row))

    def add(self, *, operation_id: str, operation_type: str,
            result_entity_id: str, result_json: str, processed_at: str) -> None:
        self.execute(
            "INSERT INTO cash_processed_operations VALUES(?,?,?,?,?)",
            (operation_id, operation_type, result_entity_id, result_json, processed_at))


class CashCutRepository(_Repository):
    def add(self, cut: XCut | ZCut) -> None:
        is_z = isinstance(cut, ZCut)
        self.execute(
            """INSERT INTO cash_cuts
            (id,shift_id,branch_id,cut_type,document_number,snapshot_json,generated_by,expected_cash,counted_cash,
             difference,blind_count_id,operation_id,is_final,generated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (cut.id, cut.shift_id, cut.branch_id, "Z" if is_z else "X",
             cut.document_number, _json(cut.snapshot),
             cut.generated_by, str(cut.expected_cash),
             str(cut.counted_cash) if is_z else None,
             str(cut.difference) if is_z else None,
             cut.blind_count_id if is_z else None, cut.operation_id,
             1 if cut.final else 0, cut.generated_at))

    def get(self, cut_id: str):
        cursor = self.execute("SELECT * FROM cash_cuts WHERE id=?", (cut_id,))
        row = cursor.fetchone()
        if row is None: return None
        return dict(zip((item[0] for item in cursor.description), row))

    def get_by_operation(self, operation_id: str):
        cursor = self.execute("SELECT * FROM cash_cuts WHERE operation_id=?", (operation_id,))
        row = cursor.fetchone()
        if row is None: return None
        return dict(zip((item[0] for item in cursor.description), row))

    def find_final_for_shift(self, shift_id: str):
        cursor = self.execute(
            "SELECT * FROM cash_cuts WHERE shift_id=? AND cut_type='Z' AND is_final=1",
            (shift_id,))
        row = cursor.fetchone()
        if row is None: return None
        return dict(zip((item[0] for item in cursor.description), row))

    def list_x_for_branch(self, *, branch_id: str, limit: int = 100) -> list[dict]:
        cursor = self.execute(
            """SELECT id,shift_id,branch_id,cut_type,document_number,snapshot_json,
            generated_by,expected_cash,counted_cash,difference,blind_count_id,
            operation_id,is_final,generated_at
            FROM cash_cuts
            WHERE branch_id=? AND cut_type='X'
            ORDER BY generated_at DESC,id DESC LIMIT ?""",
            (branch_id, int(limit)),
        )
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def list_z_for_branch(self, *, branch_id: str, limit: int = 100) -> list[dict]:
        cursor = self.execute(
            """SELECT id,shift_id,branch_id,cut_type,document_number,snapshot_json,
            generated_by,expected_cash,counted_cash,difference,blind_count_id,
            operation_id,is_final,generated_at
            FROM cash_cuts
            WHERE branch_id=? AND cut_type='Z'
            ORDER BY generated_at DESC,id DESC LIMIT ?""",
            (branch_id, int(limit)),
        )
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


class CashDifferenceRepository(_Repository):
    def add(self, difference: CashDifference) -> None:
        self.execute(
            """INSERT INTO cash_differences
            (id,shift_id,z_cut_id,branch_id,expected_amount,counted_amount,amount,
             detected_by,operation_id,responsible_user_id,classification,severity,
             tolerance_amount,recurrence_count,status,explanation,explained_by,
             reviewed_by,resolution,resolved_by)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (difference.id, difference.shift_id, difference.z_cut_id,
             difference.branch_id, str(difference.expected_amount),
             str(difference.counted_amount), str(difference.amount),
             difference.detected_by, difference.operation_id,
             difference.responsible_user_id, difference.classification.value,
             difference.severity.value, str(difference.tolerance_amount),
             difference.recurrence_count, difference.status.value,
             difference.explanation, difference.explained_by,
             difference.reviewed_by, difference.resolution,
             difference.resolved_by))

    def find_by_z_cut(self, z_cut_id: str):
        cursor = self.execute("SELECT * FROM cash_differences WHERE z_cut_id=?", (z_cut_id,))
        row = cursor.fetchone()
        if row is None: return None
        return dict(zip((item[0] for item in cursor.description), row))

    def get(self, difference_id: str):
        cursor = self.execute("SELECT * FROM cash_differences WHERE id=?", (difference_id,))
        row = cursor.fetchone()
        if row is None: return None
        return dict(zip((item[0] for item in cursor.description), row))

    def list_for_branch(self, *, branch_id: str, limit: int = 100) -> list[dict]:
        cursor = self.execute(
            """SELECT id,shift_id,z_cut_id,branch_id,expected_amount,counted_amount,amount,
            detected_by,responsible_user_id,classification,severity,tolerance_amount,
            recurrence_count,status,explanation,explained_by,reviewed_by,resolution,resolved_by
            FROM cash_differences
            WHERE branch_id=?
            ORDER BY CASE status
                WHEN 'DETECTED' THEN 0
                WHEN 'EXPLAINED' THEN 1
                WHEN 'UNDER_REVIEW' THEN 2
                ELSE 3 END,
                recurrence_count DESC,id DESC
            LIMIT ?""",
            (branch_id, int(limit)),
        )
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def recurrence_count(self, *, branch_id: str, responsible_user_id: str,
                         since: str) -> int:
        return int(self.execute(
            """SELECT COUNT(*) FROM cash_differences d JOIN cash_cuts z ON z.id=d.z_cut_id
            WHERE d.branch_id=? AND d.responsible_user_id=? AND z.generated_at>=?""",
            (branch_id, responsible_user_id, since)).fetchone()[0])

    def transition(self, *, difference_id: str, source_status: str,
                   target_status: str, values: dict[str, object]) -> None:
        allowed = {"explanation", "explained_by", "reviewed_by", "resolution", "resolved_by"}
        if not values or not set(values) <= allowed:
            raise ValueError("Invalid difference transition fields")
        assignments = ",".join(f"{key}=?" for key in values)
        cursor = self.execute(
            f"UPDATE cash_differences SET status=?,{assignments} WHERE id=? AND status=?",
            (target_status, *values.values(), difference_id, source_status))
        if cursor.rowcount != 1:
            raise RuntimeError("Concurrent or invalid difference transition")


class CashDifferencePolicyRepository(_Repository):
    def resolve(self, *, branch_id: str, occurred_at: str):
        cursor = self.execute(
            """SELECT * FROM cash_difference_policies WHERE active=1
            AND effective_from<=? AND (effective_to IS NULL OR effective_to>?)
            AND ((scope_type='BRANCH' AND scope_id=?) OR scope_type='SYSTEM')
            ORDER BY CASE scope_type WHEN 'BRANCH' THEN 0 ELSE 1 END,effective_from DESC LIMIT 1""",
            (occurred_at, occurred_at, branch_id))
        row = cursor.fetchone()
        if row is None: return None
        return dict(zip((item[0] for item in cursor.description), row))


class CashEventRepository(_Repository):
    def add(self, event: dict[str, object]) -> None:
        self.execute(
            """INSERT INTO cash_domain_events
            (id,event_name,operation_id,entity_id,branch_id,user_id,occurred_at,payload_json)
            VALUES (?,?,?,?,?,?,?,?)""",
            (event["event_id"], event["event_name"], event["operation_id"],
             event["entity_id"], event["branch_id"], event["user_id"],
             event["timestamp"], _json(event["payload"])))


class CashOutboxRepository(_Repository):
    def enqueue(self, event: dict[str, object]) -> str:
        outbox_id = new_uuid()
        self.execute(
            """INSERT INTO cash_outbox
            (id,event_id,event_name,operation_id,entity_id,payload_json,status,created_at)
            VALUES (?,?,?,?,?,?,'PENDING',?)""",
            (outbox_id, event["event_id"], event["event_name"], event["operation_id"],
             event["entity_id"], _json(event), event["timestamp"]))
        return outbox_id


class CashSyncRepository(_Repository):
    """Persistence for ordered, resumable delivery of canonical outbox rows."""

    def register_device(self, *, device_id: str, branch_id: str, now: str,
                        online: bool = True) -> None:
        self.execute(
            """INSERT INTO cash_sync_devices
            (id,branch_id,local_sequence,last_synced_sequence,connectivity,sync_status,updated_at)
            VALUES(?,?,0,0,?,'IDLE',?)
            ON CONFLICT(id) DO NOTHING""",
            (device_id, branch_id, "ONLINE" if online else "OFFLINE", now),
        )

    def get_device(self, device_id: str):
        cursor = self.execute("SELECT * FROM cash_sync_devices WHERE id=?", (device_id,))
        row = cursor.fetchone()
        return None if row is None else dict(zip((item[0] for item in cursor.description), row))

    def set_connectivity(self, *, device_id: str, online: bool, now: str) -> None:
        status = "IDLE" if online else "IDLE"
        cursor = self.execute(
            "UPDATE cash_sync_devices SET connectivity=?,sync_status=?,updated_at=? WHERE id=?",
            ("ONLINE" if online else "OFFLINE", status, now, device_id),
        )
        if cursor.rowcount != 1:
            raise LookupError("Sync device not found")

    def stage_pending(self, *, device_id: str, branch_id: str, now: str,
                      limit: int = 100) -> int:
        device = self.get_device(device_id)
        if device is None or device["branch_id"] != branch_id:
            raise LookupError("Sync device outside branch scope")
        rows = self.execute(
            """SELECT o.id FROM cash_outbox o
            JOIN cash_domain_events e ON e.id=o.event_id
            LEFT JOIN cash_sync_envelopes s ON s.outbox_id=o.id
            WHERE e.branch_id=? AND s.id IS NULL
            ORDER BY o.created_at,o.id LIMIT ?""",
            (branch_id, limit),
        ).fetchall()
        sequence = int(device["local_sequence"])
        for (outbox_id,) in rows:
            sequence += 1
            self.execute(
                """INSERT INTO cash_sync_envelopes
                (id,outbox_id,device_id,sequence_no,aggregate_version,state,created_at)
                VALUES(?,?,?,?,1,'PENDING',?)""",
                (new_uuid(), outbox_id, device_id, sequence, now),
            )
        if rows:
            self.execute(
                "UPDATE cash_sync_devices SET local_sequence=?,updated_at=? WHERE id=?",
                (sequence, now, device_id),
            )
        return len(rows)

    def list_ready(self, *, device_id: str, now: str, limit: int) -> list[dict]:
        cursor = self.execute(
            """SELECT s.id,s.outbox_id,s.sequence_no,s.aggregate_version,
                      s.attempt_count,o.event_name,o.operation_id,o.entity_id,o.payload_json
            FROM cash_sync_envelopes s JOIN cash_outbox o ON o.id=s.outbox_id
            WHERE s.device_id=? AND s.state IN ('PENDING','RETRY')
              AND (s.next_attempt_at IS NULL OR s.next_attempt_at<=?)
              AND NOT EXISTS (SELECT 1 FROM cash_sync_envelopes blocked
                              WHERE blocked.device_id=s.device_id AND blocked.state='CONFLICT')
            ORDER BY s.sequence_no LIMIT ?""",
            (device_id, now, limit),
        )
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def mark_in_flight(self, envelope_ids: list[str]) -> None:
        for envelope_id in envelope_ids:
            cursor = self.execute(
                """UPDATE cash_sync_envelopes SET state='IN_FLIGHT',attempt_count=attempt_count+1
                WHERE id=? AND state IN ('PENDING','RETRY')""", (envelope_id,))
            if cursor.rowcount != 1:
                raise RuntimeError("Sync envelope was claimed concurrently")

    def mark_synced(self, *, envelope_id: str, device_id: str,
                    sequence_no: int, remote_revision: str, now: str) -> None:
        self.execute(
            """UPDATE cash_sync_envelopes SET state='SYNCED',remote_revision=?,synced_at=?,next_attempt_at=NULL
            WHERE id=? AND state='IN_FLIGHT'""", (remote_revision, now, envelope_id))
        self.execute(
            """UPDATE cash_outbox SET status='DISPATCHED',dispatched_at=?,last_error=NULL
            WHERE id=(SELECT outbox_id FROM cash_sync_envelopes WHERE id=?)""",
            (now, envelope_id),
        )
        self.execute(
            """UPDATE cash_sync_devices SET last_synced_sequence=
            CASE WHEN last_synced_sequence>? THEN last_synced_sequence ELSE ? END,
            sync_status='SYNCING',last_error=NULL,last_sync_at=?,updated_at=? WHERE id=?""",
            (sequence_no, sequence_no, now, now, device_id),
        )

    def mark_retry(self, *, envelope_id: str, next_attempt_at: str,
                   error: str) -> None:
        self.execute(
            """UPDATE cash_sync_envelopes SET state='RETRY',next_attempt_at=?
            WHERE id=? AND state='IN_FLIGHT'""", (next_attempt_at, envelope_id))
        self.execute(
            """UPDATE cash_outbox SET status='FAILED',attempt_count=attempt_count+1,
            next_attempt_at=?,last_error=? WHERE id=(SELECT outbox_id FROM cash_sync_envelopes WHERE id=?)""",
            (next_attempt_at, error, envelope_id),
        )

    def mark_conflict(self, *, envelope_id: str, remote_revision: str,
                      conflict: dict) -> None:
        self.execute(
            """UPDATE cash_sync_envelopes SET state='CONFLICT',remote_revision=?,conflict_json=?
            WHERE id=? AND state='IN_FLIGHT'""",
            (remote_revision, _json(conflict), envelope_id),
        )
        self.execute(
            """UPDATE cash_outbox SET status='FAILED',last_error='SYNC_CONFLICT'
            WHERE id=(SELECT outbox_id FROM cash_sync_envelopes WHERE id=?)""", (envelope_id,))

    def finish_cycle(self, *, device_id: str, status: str, now: str,
                     error: str | None = None) -> None:
        if status not in {"IDLE", "RETRYING", "CONFLICT", "ERROR"}:
            raise ValueError("Invalid final sync status")
        self.execute(
            "UPDATE cash_sync_devices SET sync_status=?,last_error=?,updated_at=? WHERE id=?",
            (status, error, now, device_id),
        )

    def state(self, device_id: str) -> dict:
        device = self.get_device(device_id)
        if device is None:
            raise LookupError("Sync device not found")
        counts = dict(self.execute(
            "SELECT state,COUNT(*) FROM cash_sync_envelopes WHERE device_id=? GROUP BY state",
            (device_id,),
        ).fetchall())
        return {**device, "pending_count": counts.get("PENDING", 0) + counts.get("RETRY", 0),
                "conflict_count": counts.get("CONFLICT", 0),
                "synced_count": counts.get("SYNCED", 0)}

    def list_recent(self, *, device_id: str, limit: int = 100) -> list[dict]:
        cursor = self.execute(
            """SELECT s.id,s.sequence_no,s.aggregate_version,s.state,s.attempt_count,
                      s.next_attempt_at,s.remote_revision,s.created_at,s.synced_at,
                      o.event_name,o.operation_id,o.entity_id,o.last_error
            FROM cash_sync_envelopes s JOIN cash_outbox o ON o.id=s.outbox_id
            WHERE s.device_id=?
            ORDER BY s.sequence_no DESC LIMIT ?""",
            (device_id, limit),
        )
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def list_conflicts(self, *, device_id: str) -> list[dict]:
        cursor = self.execute(
            """SELECT s.id,s.sequence_no,s.aggregate_version,s.state,s.attempt_count,
                      s.remote_revision,s.conflict_json,s.created_at,
                      o.event_name,o.operation_id,o.entity_id,o.last_error
            FROM cash_sync_envelopes s JOIN cash_outbox o ON o.id=s.outbox_id
            WHERE s.device_id=? AND s.state='CONFLICT'
            ORDER BY s.sequence_no""",
            (device_id,),
        )
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_envelope(self, envelope_id: str):
        cursor = self.execute("SELECT * FROM cash_sync_envelopes WHERE id=?", (envelope_id,))
        row = cursor.fetchone()
        return None if row is None else dict(zip((item[0] for item in cursor.description), row))

    def resolve_conflict(self, *, envelope_id: str, strategy: str,
                         now: str) -> None:
        envelope = self.get_envelope(envelope_id)
        if envelope is None:
            raise LookupError("Sync conflict not found")
        if strategy == "RETRY_LOCAL":
            cursor = self.execute(
                """UPDATE cash_sync_envelopes SET state='RETRY',aggregate_version=aggregate_version+1,
                next_attempt_at=?,conflict_json=NULL WHERE id=? AND state='CONFLICT'""",
                (now, envelope_id),
            )
            self.execute(
                """UPDATE cash_outbox SET status='FAILED',next_attempt_at=?,last_error='CONFLICT_RETRY'
                WHERE id=(SELECT outbox_id FROM cash_sync_envelopes WHERE id=?)""",
                (now, envelope_id),
            )
        elif strategy == "ACCEPT_REMOTE":
            cursor = self.execute(
                """UPDATE cash_sync_envelopes SET state='SYNCED',synced_at=?,conflict_json=NULL
                WHERE id=? AND state='CONFLICT'""", (now, envelope_id))
            self.execute(
                """UPDATE cash_outbox SET status='DISPATCHED',dispatched_at=?,last_error=NULL
                WHERE id=(SELECT outbox_id FROM cash_sync_envelopes WHERE id=?)""",
                (now, envelope_id),
            )
        else:
            raise ValueError("Unknown conflict strategy")
        if cursor.rowcount != 1:
            raise RuntimeError("Conflict is no longer pending")
        if strategy == "ACCEPT_REMOTE":
            self.execute(
                """UPDATE cash_sync_devices SET last_synced_sequence=
                CASE WHEN last_synced_sequence>? THEN last_synced_sequence ELSE ? END,
                sync_status='IDLE',last_error=NULL,updated_at=? WHERE id=?""",
                (envelope["sequence_no"], envelope["sequence_no"], now,
                 envelope["device_id"]),
            )
        else:
            self.execute(
                "UPDATE cash_sync_devices SET sync_status='RETRYING',last_error=NULL,updated_at=? WHERE id=?",
                (now, envelope["device_id"]),
            )
