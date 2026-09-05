"""ProcessStepExecutionRepository — persists ProcessStepExecution entities (§20)."""

from __future__ import annotations

from backend.domain.meat_processing.entities.process_step_execution import ProcessStepExecution
from backend.domain.meat_processing.enums import ExecutionStatus
from backend.infrastructure.db.repositories.meat_processing.base import (
    MeatProcessingRepositoryBase,
    dt_str,
    enum_value,
    parse_dt,
)


def _to_entity(row: dict) -> ProcessStepExecution:
    return ProcessStepExecution(
        id=row["id"], operation_id=row["operation_id"],
        process_execution_id=row["process_execution_id"], step_name=row["step_name"],
        sequence=row["sequence"], status=ExecutionStatus(row["status"]),
        started_at=parse_dt(row["started_at"]), completed_at=parse_dt(row["completed_at"]),
        created_at=parse_dt(row["created_at"]))


class ProcessStepExecutionRepository(MeatProcessingRepositoryBase):
    def save(self, step: ProcessStepExecution) -> None:
        self._execute(
            "INSERT INTO process_step_executions (id, operation_id, process_execution_id,"
            " step_name, sequence, status, started_at, completed_at, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET status=excluded.status,"
            " started_at=excluded.started_at, completed_at=excluded.completed_at",
            (step.id, step.operation_id, step.process_execution_id, step.step_name,
             step.sequence, enum_value(step.status), dt_str(step.started_at),
             dt_str(step.completed_at), dt_str(step.created_at)))

    def get(self, step_id: str) -> ProcessStepExecution | None:
        row = self._query_one(
            "SELECT * FROM process_step_executions WHERE id=?", (step_id,))
        return None if row is None else _to_entity(row)

    def list_by_execution(self, process_execution_id: str) -> list[ProcessStepExecution]:
        rows = self._query(
            "SELECT * FROM process_step_executions WHERE process_execution_id=?"
            " ORDER BY sequence, created_at", (process_execution_id,))
        return [_to_entity(row) for row in rows]
