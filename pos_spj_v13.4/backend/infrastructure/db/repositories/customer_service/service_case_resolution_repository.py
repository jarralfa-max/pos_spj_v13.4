"""ServiceCaseResolutionRepository — persists the resolution evidence."""

from __future__ import annotations

from backend.domain.customer_service.entities.service_case_resolution import (
    ServiceCaseResolution,
)
from backend.infrastructure.db.repositories.customer_service.base import (
    CustomerServiceRepositoryBase,
)

_RESOLUTION_COLS = (
    "id, case_id, resolution_summary, resolved_by_user_id, root_cause,"
    " customer_satisfied, created_at"
)


class ServiceCaseResolutionRepository(CustomerServiceRepositoryBase):
    def save(self, resolution: ServiceCaseResolution) -> None:
        self._execute(
            f"INSERT INTO service_case_resolutions ({_RESOLUTION_COLS}) VALUES (?,?,?,?,?,?,?)",
            (resolution.id, resolution.case_id, resolution.resolution_summary,
             resolution.resolved_by_user_id, resolution.root_cause,
             (int(resolution.customer_satisfied)
              if resolution.customer_satisfied is not None else None),
             resolution.created_at))

    def get_for_case(self, case_id: str) -> ServiceCaseResolution | None:
        row = self._query_one(
            f"SELECT {_RESOLUTION_COLS} FROM service_case_resolutions"
            " WHERE case_id=? ORDER BY created_at DESC LIMIT 1", (case_id,))
        return self._hydrate(row) if row else None

    @staticmethod
    def _hydrate(row: dict) -> ServiceCaseResolution:
        return ServiceCaseResolution(
            id=row["id"], case_id=row["case_id"], resolution_summary=row["resolution_summary"],
            resolved_by_user_id=row["resolved_by_user_id"], root_cause=row["root_cause"] or "",
            customer_satisfied=(bool(row["customer_satisfied"])
                                if row["customer_satisfied"] is not None else None),
            created_at=row["created_at"],
        )
