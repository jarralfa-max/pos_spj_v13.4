"""Persistencia de las asignaciones de costo de producción y del outbox de Costos."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from backend.shared.ids import new_uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _txt(value) -> str | None:
    return None if value is None else str(value)


@dataclass(frozen=True)
class StoredAllocationLine:
    line_kind: str
    product_id: str
    output_type: str | None
    lot_id: str | None
    quantity: Decimal
    unit_price: Decimal | None
    basis_value: Decimal
    allocated_cost: Decimal
    unit_cost: Decimal


@dataclass(frozen=True)
class StoredAllocation:
    id: str
    operation_id: str
    processing_order_id: str
    branch_id: str
    process_type: str
    method: str
    currency_code: str
    input_cost_total: Decimal
    output_value_total: Decimal
    waste_value_total: Decimal
    created_by_user_id: str
    created_at: str
    lines: tuple[StoredAllocationLine, ...]


class ProcessingCostRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    def add(self, *, allocation_id: str, operation_id: str, processing_order_id: str,
            source_module: str, branch_id: str, process_type: str, method: str,
            currency_code: str, input_cost_total: Decimal, output_value_total: Decimal,
            waste_value_total: Decimal, created_by_user_id: str,
            lines: list[StoredAllocationLine]) -> None:
        self._conn.execute(
            "INSERT INTO processing_cost_allocations (id, operation_id, processing_order_id,"
            " source_module, branch_id, process_type, method, currency_code, input_cost_total,"
            " output_value_total, waste_value_total, created_by_user_id, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (allocation_id, operation_id, processing_order_id, source_module, branch_id,
             process_type, method, currency_code, str(input_cost_total),
             str(output_value_total), str(waste_value_total), created_by_user_id, _now()))
        for linea in lines:
            self._conn.execute(
                "INSERT INTO processing_cost_allocation_lines (id, allocation_id, line_kind,"
                " product_id, output_type, lot_id, quantity, unit_price, basis_value,"
                " allocated_cost, unit_cost) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (new_uuid(), allocation_id, linea.line_kind, linea.product_id,
                 linea.output_type, linea.lot_id, str(linea.quantity), _txt(linea.unit_price),
                 str(linea.basis_value), str(linea.allocated_cost), str(linea.unit_cost)))

    def get_by_order(self, processing_order_id: str) -> StoredAllocation | None:
        fila = self._conn.execute(
            "SELECT id, operation_id, processing_order_id, branch_id, process_type, method,"
            " currency_code, input_cost_total, output_value_total, waste_value_total,"
            " created_by_user_id, created_at FROM processing_cost_allocations"
            " WHERE processing_order_id=?", (processing_order_id,)).fetchone()
        if fila is None:
            return None
        f = tuple(fila)
        lineas = tuple(
            StoredAllocationLine(r[0], r[1], r[2], r[3], Decimal(str(r[4])),
                                 None if r[5] is None else Decimal(str(r[5])),
                                 Decimal(str(r[6])), Decimal(str(r[7])), Decimal(str(r[8])))
            for r in self._conn.execute(
                "SELECT line_kind, product_id, output_type, lot_id, quantity, unit_price,"
                " basis_value, allocated_cost, unit_cost FROM processing_cost_allocation_lines"
                " WHERE allocation_id=? ORDER BY line_kind, product_id", (f[0],)).fetchall())
        return StoredAllocation(f[0], f[1], f[2], f[3], f[4], f[5], f[6], Decimal(str(f[7])),
                                Decimal(str(f[8])), Decimal(str(f[9])), f[10], f[11], lineas)


class CostingOutboxRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    def enqueue(self, *, event_id: str, event_name: str, payload: dict,
                operation_id: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO costing_outbox (id, event_id, event_name, payload_json,"
            " operation_id, status, created_at) VALUES (?,?,?,?,?,'PENDING',?)",
            (new_uuid(), event_id, event_name, json.dumps(payload), operation_id, _now()))

    def list_pending(self, *, limit: int = 500) -> list[dict]:
        cur = self._conn.execute(
            "SELECT id, event_id, event_name, payload_json, operation_id, attempts"
            " FROM costing_outbox WHERE status='PENDING' ORDER BY created_at, id LIMIT ?",
            (limit,))
        columnas = [c[0] for c in cur.description]
        return [dict(zip(columnas, r)) for r in cur.fetchall()]

    def list_for_operation(self, operation_id: str) -> list[dict]:
        cur = self._conn.execute(
            "SELECT event_id, event_name, payload_json, status FROM costing_outbox"
            " WHERE operation_id=? ORDER BY created_at, id", (operation_id,))
        columnas = [c[0] for c in cur.description]
        return [dict(zip(columnas, r)) for r in cur.fetchall()]

    def mark_dispatched(self, outbox_id: str) -> None:
        self._conn.execute(
            "UPDATE costing_outbox SET status='DISPATCHED', dispatched_at=? WHERE id=?",
            (_now(), outbox_id))

    def mark_failed(self, outbox_id: str, error: str) -> None:
        self._conn.execute(
            "UPDATE costing_outbox SET attempts=attempts+1, last_error=? WHERE id=?",
            (str(error)[:500], outbox_id))
