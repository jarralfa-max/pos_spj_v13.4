"""SqliteBranchProfileRepository — persists `BranchProfile` (SET-5).
Implements
`backend.domain.settings.repository_ports.BranchProfileRepositoryPort`.
"""

from __future__ import annotations

import json
from datetime import time
from decimal import Decimal

from backend.domain.settings.entities.branch_profile import BranchProfile
from backend.domain.settings.value_objects.map_reference import MapReference
from backend.infrastructure.db.repositories.settings.base import SettingsRepositoryBase

_COLS = (
    "id, branch_id, code, name, address, phone, timezone, locale, opening_time,"
    " closing_time, operation_days_json, warehouse_ids_json, default_workstation_profile_id,"
    " ticket_header, ticket_footer, social_links_json, map_latitude, map_longitude,"
    " map_place_id, active, created_at, updated_at"
)


class SqliteBranchProfileRepository(SettingsRepositoryBase):
    def save(self, profile: BranchProfile) -> None:
        self._execute(
            f"INSERT INTO branch_profiles ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " code=excluded.code, name=excluded.name, address=excluded.address,"
            " phone=excluded.phone, timezone=excluded.timezone, locale=excluded.locale,"
            " opening_time=excluded.opening_time, closing_time=excluded.closing_time,"
            " operation_days_json=excluded.operation_days_json,"
            " warehouse_ids_json=excluded.warehouse_ids_json,"
            " default_workstation_profile_id=excluded.default_workstation_profile_id,"
            " ticket_header=excluded.ticket_header, ticket_footer=excluded.ticket_footer,"
            " social_links_json=excluded.social_links_json, map_latitude=excluded.map_latitude,"
            " map_longitude=excluded.map_longitude, map_place_id=excluded.map_place_id,"
            " active=excluded.active, updated_at=excluded.updated_at",
            self._params(profile),
        )

    def get(self, branch_id: str) -> BranchProfile | None:
        row = self._query_one(f"SELECT {_COLS} FROM branch_profiles WHERE branch_id=?", (branch_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> BranchProfile | None:
        row = self._query_one(f"SELECT {_COLS} FROM branch_profiles WHERE code=?", (code,))
        return self._hydrate(row) if row else None

    def list_active(self) -> list[BranchProfile]:
        rows = self._query(f"SELECT {_COLS} FROM branch_profiles WHERE active=1 ORDER BY code")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(profile: BranchProfile) -> tuple:
        return (
            profile.id, profile.branch_id, profile.code, profile.name, profile.address,
            profile.phone, profile.timezone, profile.locale,
            profile.opening_time.isoformat() if profile.opening_time else None,
            profile.closing_time.isoformat() if profile.closing_time else None,
            json.dumps(list(profile.operation_days)), json.dumps(list(profile.warehouse_ids)),
            profile.default_workstation_profile_id, profile.ticket_header, profile.ticket_footer,
            json.dumps(profile.social_links),
            str(profile.map_reference.latitude) if profile.map_reference.latitude is not None else None,
            str(profile.map_reference.longitude) if profile.map_reference.longitude is not None else None,
            profile.map_reference.place_id,
            int(profile.active), profile.created_at, profile.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> BranchProfile:
        return BranchProfile(
            id=row["id"], branch_id=row["branch_id"], code=row["code"], name=row["name"],
            address=row["address"] or "", phone=row["phone"], timezone=row["timezone"] or "",
            locale=row["locale"] or "",
            opening_time=time.fromisoformat(row["opening_time"]) if row["opening_time"] else None,
            closing_time=time.fromisoformat(row["closing_time"]) if row["closing_time"] else None,
            operation_days=tuple(json.loads(row["operation_days_json"] or "[]")),
            warehouse_ids=tuple(json.loads(row["warehouse_ids_json"] or "[]")),
            default_workstation_profile_id=row["default_workstation_profile_id"],
            ticket_header=row["ticket_header"] or "", ticket_footer=row["ticket_footer"] or "",
            social_links=json.loads(row["social_links_json"] or "{}"),
            map_reference=MapReference(
                latitude=Decimal(row["map_latitude"]) if row["map_latitude"] else None,
                longitude=Decimal(row["map_longitude"]) if row["map_longitude"] else None,
                place_id=row["map_place_id"],
            ),
            active=bool(row["active"]), created_at=row["created_at"], updated_at=row["updated_at"],
        )
