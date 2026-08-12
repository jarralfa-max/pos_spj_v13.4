"""ProcessExecutionRepository — persists ProcessExecution aggregates (§20)."""

from __future__ import annotations

from backend.domain.meat_processing.entities.process_execution import ProcessExecution
from backend.domain.meat_processing.enums import ExecutionStatus
from backend.infrastructure.db.repositories.meat_processing.base import (
    MeatProcessingRepositoryBase,
    dec_str,
    dt_str,
    enum_value,
    parse_dt,
    to_decimal,
)


def _to_entity(row: dict) -> ProcessExecution:
    return ProcessExecution(
        id=row["id"], operation_id=row["operation_id"],
        processing_order_id=row["processing_order_id"],
        processing_batch_id=row["processing_batch_id"], work_center_id=row["work_center_id"],
        status=ExecutionStatus(row["status"]), started_at=parse_dt(row["started_at"]),
        paused_at=parse_dt(row["paused_at"]), resumed_at=parse_dt(row["resumed_at"]),
        completed_at=parse_dt(row["completed_at"]),
        total_paused_seconds=to_decimal(row["total_paused_seconds"]),
        created_at=parse_dt(row["created_at"]))


class ProcessExecutionRepository(MeatProcessingRepositoryBase):
    def save(self, execution: ProcessExecution) -> None:
        self._execute(
            "INSERT INTO process_executions (id, operation_id, processing_order_id,"
            " processing_batch_id, work_center_id, status, started_at, paused_at,"
            " resumed_at, completed_at, total_paused_seconds, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET status=excluded.status,"
            " started_at=excluded.started_at, paused_at=excluded.paused_at,"
            " resumed_at=excluded.resumed_at, completed_at=excluded.completed_at,"
            " total_paused_seconds=excluded.total_paused_seconds",
            (execution.id, execution.operation_id, execution.processing_order_id,
             execution.processing_batch_id, execution.work_center_id,
             enum_value(execution.status), dt_str(execution.started_at),
             dt_str(execution.paused_at), dt_str(execution.resumed_at),
             dt_str(execution.completed_at), dec_str(execution.total_paused_seconds),
             dt_str(execution.created_at)))

    def get(self, execution_id: str) -> ProcessExecution | None:
        row = self._query_one("SELECT * FROM process_executions WHERE id=?", (execution_id,))
        return None if row is None else _to_entity(row)

    def list_by_order(self, processing_order_id: str) -> list[ProcessExecution]:
        rows = self._query(
            "SELECT * FROM process_executions WHERE processing_order_id=?"
            " ORDER BY created_at", (processing_order_id,))
        return [_to_entity(row) for row in rows]

    def list_by_batch(self, processing_batch_id: str) -> list[ProcessExecution]:
        rows = self._query(
            "SELECT * FROM process_executions WHERE processing_batch_id=?"
            " ORDER BY created_at", (processing_batch_id,))
        return [_to_entity(row) for row in rows]
