"""Reservas reales por requerimiento y bitácora de pasos de la ejecución.

`ExecutionStepRepository` es lo que hace reanudable e idempotente a la
ejecución sin fabricar identidades: cada paso que llama a otro contexto obtiene
su `operation_id` (UUIDv7) UNA vez, lo guarda ANTES de llamar y lo reutiliza en
cada reintento. El contexto dueño reconoce ese mismo `operation_id` y no
duplica el movimiento, el lote, el costeo ni la merma.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from backend.shared.ids import new_uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class RequirementAllocation:
    id: str
    material_requirement_id: str
    processing_order_id: str
    product_id: str
    inventory_reservation_id: str
    allocated_lot_id: str | None
    allocated_location_id: str | None
    quantity: Decimal
    status: str
    material_consumption_id: str | None


class MaterialRequirementAllocationRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    def add(self, *, material_requirement_id: str, processing_order_id: str,
            product_id: str, inventory_reservation_id: str, lot_id: str | None,
            location_id: str | None, quantity: Decimal) -> str:
        existente = self._conn.execute(
            "SELECT id FROM material_requirement_allocations WHERE inventory_reservation_id=?",
            (inventory_reservation_id,)).fetchone()
        if existente is not None:
            return str(existente[0])
        fila_id, ahora = new_uuid(), _now()
        self._conn.execute(
            "INSERT INTO material_requirement_allocations (id, material_requirement_id,"
            " processing_order_id, product_id, inventory_reservation_id, allocated_lot_id,"
            " allocated_location_id, quantity, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,'RESERVED',?,?)",
            (fila_id, material_requirement_id, processing_order_id, product_id,
             inventory_reservation_id, lot_id, location_id, str(quantity), ahora, ahora))
        return fila_id

    def list_by_order(self, processing_order_id: str) -> list[RequirementAllocation]:
        return self._list("processing_order_id=?", (processing_order_id,))

    def list_by_requirement(self, material_requirement_id: str) -> list[RequirementAllocation]:
        return self._list("material_requirement_id=?", (material_requirement_id,))

    def attach_consumption(self, allocation_id: str, material_consumption_id: str) -> None:
        self._conn.execute(
            "UPDATE material_requirement_allocations SET material_consumption_id=?,"
            " updated_at=? WHERE id=? AND material_consumption_id IS NULL",
            (material_consumption_id, _now(), allocation_id))

    def mark_consumed(self, allocation_id: str) -> None:
        self._conn.execute(
            "UPDATE material_requirement_allocations SET status='CONSUMED', updated_at=?"
            " WHERE id=?", (_now(), allocation_id))

    def get_by_consumption(self, material_consumption_id: str) -> RequirementAllocation | None:
        filas = self._list("material_consumption_id=?", (material_consumption_id,))
        return filas[0] if filas else None

    def mark_released(self, allocation_id: str) -> None:
        self._conn.execute(
            "UPDATE material_requirement_allocations SET status='RELEASED', updated_at=?"
            " WHERE id=? AND status='RESERVED'", (_now(), allocation_id))

    def _list(self, where: str, params) -> list[RequirementAllocation]:
        filas = self._conn.execute(
            "SELECT id, material_requirement_id, processing_order_id, product_id,"
            " inventory_reservation_id, allocated_lot_id, allocated_location_id, quantity,"
            " status, material_consumption_id FROM material_requirement_allocations"
            f" WHERE {where} ORDER BY created_at, id", params).fetchall()
        return [RequirementAllocation(r[0], r[1], r[2], r[3], r[4], r[5], r[6],
                                      Decimal(str(r[7])), r[8], r[9]) for r in filas]


@dataclass(frozen=True)
class ExecutionStep:
    id: str
    processing_order_id: str
    step: str
    target_id: str
    operation_id: str
    status: str
    result_reference: str | None
    attempts: int
    last_error: str | None

    @property
    def done(self) -> bool:
        return self.status == "DONE"


class ExecutionStepRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    def begin(self, processing_order_id: str, step: str, target_id: str) -> ExecutionStep:
        """El paso con su `operation_id` estable: se crea la primera vez y se
        devuelve tal cual en cada reintento."""
        actual = self.get(processing_order_id, step, target_id)
        if actual is not None:
            if not actual.done:
                self._conn.execute(
                    "UPDATE processing_execution_steps SET attempts=attempts+1, updated_at=?"
                    " WHERE id=?", (_now(), actual.id))
            return self.get(processing_order_id, step, target_id)
        ahora = _now()
        self._conn.execute(
            "INSERT INTO processing_execution_steps (id, processing_order_id, step, target_id,"
            " operation_id, status, attempts, created_at, updated_at)"
            " VALUES (?,?,?,?,?,'PENDING',1,?,?)",
            (new_uuid(), processing_order_id, step, target_id, new_uuid(), ahora, ahora))
        return self.get(processing_order_id, step, target_id)

    def complete(self, step: ExecutionStep, result_reference: str | None) -> None:
        self._conn.execute(
            "UPDATE processing_execution_steps SET status='DONE', result_reference=?,"
            " last_error=NULL, updated_at=? WHERE id=?",
            (result_reference, _now(), step.id))

    def fail(self, step: ExecutionStep, error: str) -> None:
        self._conn.execute(
            "UPDATE processing_execution_steps SET status='FAILED', last_error=?, updated_at=?"
            " WHERE id=?", (str(error)[:500], _now(), step.id))

    def get(self, processing_order_id: str, step: str, target_id: str) -> ExecutionStep | None:
        fila = self._conn.execute(
            "SELECT id, processing_order_id, step, target_id, operation_id, status,"
            " result_reference, attempts, last_error FROM processing_execution_steps"
            " WHERE processing_order_id=? AND step=? AND target_id=?",
            (processing_order_id, step, target_id)).fetchone()
        return None if fila is None else ExecutionStep(*tuple(fila))

    def list_by_order(self, processing_order_id: str) -> list[ExecutionStep]:
        return [ExecutionStep(*tuple(f)) for f in self._conn.execute(
            "SELECT id, processing_order_id, step, target_id, operation_id, status,"
            " result_reference, attempts, last_error FROM processing_execution_steps"
            " WHERE processing_order_id=? ORDER BY created_at, id",
            (processing_order_id,)).fetchall()]
