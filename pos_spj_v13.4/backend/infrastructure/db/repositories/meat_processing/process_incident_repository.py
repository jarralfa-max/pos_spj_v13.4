"""ProcessIncidentRepository — persists ProcessIncident entities (§30)."""

from __future__ import annotations

from backend.domain.meat_processing.entities.process_incident import ProcessIncident
from backend.domain.meat_processing.enums import IncidentStatus, IncidentType
from backend.infrastructure.db.repositories.meat_processing.base import (
    MeatProcessingRepositoryBase,
    dt_str,
    enum_value,
    parse_dt,
)


def _to_entity(row: dict) -> ProcessIncident:
    return ProcessIncident(
        id=row["id"], operation_id=row["operation_id"],
        processing_order_id=row["processing_order_id"],
        incident_type=IncidentType(row["incident_type"]),
        reported_by_user_id=row["reported_by_user_id"], description=row["description"],
        process_execution_id=row["process_execution_id"],
        status=IncidentStatus(row["status"]), reported_at=parse_dt(row["reported_at"]),
        resolved_by_user_id=row["resolved_by_user_id"],
        resolved_at=parse_dt(row["resolved_at"]),
        resolution_notes=row["resolution_notes"] or "")


class ProcessIncidentRepository(MeatProcessingRepositoryBase):
    def save(self, incident: ProcessIncident) -> None:
        self._execute(
            "INSERT INTO process_incidents (id, operation_id, processing_order_id,"
            " process_execution_id, incident_type, status, reported_by_user_id,"
            " description, reported_at, resolved_by_user_id, resolved_at, resolution_notes)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET status=excluded.status,"
            " resolved_by_user_id=excluded.resolved_by_user_id,"
            " resolved_at=excluded.resolved_at, resolution_notes=excluded.resolution_notes",
            (incident.id, incident.operation_id, incident.processing_order_id,
             incident.process_execution_id, enum_value(incident.incident_type),
             enum_value(incident.status), incident.reported_by_user_id, incident.description,
             dt_str(incident.reported_at), incident.resolved_by_user_id,
             dt_str(incident.resolved_at), incident.resolution_notes))

    def get(self, incident_id: str) -> ProcessIncident | None:
        row = self._query_one("SELECT * FROM process_incidents WHERE id=?", (incident_id,))
        return None if row is None else _to_entity(row)

    def list_by_order(self, processing_order_id: str) -> list[ProcessIncident]:
        rows = self._query(
            "SELECT * FROM process_incidents WHERE processing_order_id=?"
            " ORDER BY reported_at", (processing_order_id,))
        return [_to_entity(row) for row in rows]
