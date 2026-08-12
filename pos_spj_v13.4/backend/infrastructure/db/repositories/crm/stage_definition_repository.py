"""CRMStageDefinitionRepository — persists the configurable pipeline stage
catalog. Mirrors backend/infrastructure/db/repositories/crm/lead_repository.py.
"""

from __future__ import annotations

import json

from backend.domain.crm.entities.stage_definition import CRMStageDefinition
from backend.infrastructure.db.repositories.crm.base import CRMRepositoryBase

_STAGE_COLS = (
    "id, code, name, sequence_order, probability_default, is_won_stage,"
    " is_lost_stage, required_fields_json, min_activities, active,"
    " created_at, updated_at"
)


class CRMStageDefinitionRepository(CRMRepositoryBase):
    def save(self, stage: CRMStageDefinition) -> None:
        self._execute(
            f"INSERT INTO crm_stage_definitions ({_STAGE_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            self._params(stage))

    def update(self, stage: CRMStageDefinition) -> None:
        self._execute(
            "UPDATE crm_stage_definitions SET name=?, sequence_order=?,"
            " probability_default=?, is_won_stage=?, is_lost_stage=?,"
            " required_fields_json=?, min_activities=?, active=?, updated_at=?"
            " WHERE id=?",
            (stage.name, stage.sequence_order, stage.probability_default,
             int(stage.is_won_stage), int(stage.is_lost_stage),
             json.dumps(list(stage.required_fields)), stage.min_activities,
             int(stage.active), stage.updated_at, stage.id))

    def get(self, stage_id: str) -> CRMStageDefinition | None:
        row = self._query_one(
            f"SELECT {_STAGE_COLS} FROM crm_stage_definitions WHERE id=?", (stage_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> CRMStageDefinition | None:
        row = self._query_one(
            f"SELECT {_STAGE_COLS} FROM crm_stage_definitions WHERE code=?", (code.upper(),))
        return self._hydrate(row) if row else None

    def list_active_ordered(self) -> list[CRMStageDefinition]:
        rows = self._query(
            f"SELECT {_STAGE_COLS} FROM crm_stage_definitions"
            " WHERE active=1 ORDER BY sequence_order ASC")
        return [self._hydrate(r) for r in rows]

    def get_won_stage(self) -> CRMStageDefinition | None:
        row = self._query_one(
            f"SELECT {_STAGE_COLS} FROM crm_stage_definitions"
            " WHERE is_won_stage=1 AND active=1 ORDER BY sequence_order ASC LIMIT 1")
        return self._hydrate(row) if row else None

    def get_lost_stage(self) -> CRMStageDefinition | None:
        row = self._query_one(
            f"SELECT {_STAGE_COLS} FROM crm_stage_definitions"
            " WHERE is_lost_stage=1 AND active=1 ORDER BY sequence_order ASC LIMIT 1")
        return self._hydrate(row) if row else None

    def get_default_initial_stage(self) -> CRMStageDefinition | None:
        row = self._query_one(
            f"SELECT {_STAGE_COLS} FROM crm_stage_definitions"
            " WHERE active=1 AND is_won_stage=0 AND is_lost_stage=0"
            " ORDER BY sequence_order ASC LIMIT 1")
        return self._hydrate(row) if row else None

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(stage: CRMStageDefinition) -> tuple:
        return (
            stage.id, stage.code, stage.name, stage.sequence_order,
            stage.probability_default, int(stage.is_won_stage), int(stage.is_lost_stage),
            json.dumps(list(stage.required_fields)), stage.min_activities,
            int(stage.active), stage.created_at, stage.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> CRMStageDefinition:
        return CRMStageDefinition(
            id=row["id"], code=row["code"], name=row["name"],
            sequence_order=row["sequence_order"],
            probability_default=row["probability_default"],
            is_won_stage=bool(row["is_won_stage"]), is_lost_stage=bool(row["is_lost_stage"]),
            required_fields=tuple(json.loads(row["required_fields_json"] or "[]")),
            min_activities=row["min_activities"], active=bool(row["active"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
