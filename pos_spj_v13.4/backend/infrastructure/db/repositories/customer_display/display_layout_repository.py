"""SqliteDisplayLayoutRepository — persists `DisplayLayout` (SET-17).
Implements
`backend.domain.customer_display.repository_ports.DisplayLayoutRepositoryPort`.

`sections_json` serializes each `DisplaySection` as `{"code", "order",
"enabled"}` — same shape discipline as
`backend/infrastructure/db/repositories/document_output/marketing_campaign_repository.py::
_serialize_rules` (SET-13).
"""

from __future__ import annotations

import json

from backend.domain.customer_display.entities.display_layout import DisplayLayout
from backend.domain.customer_display.enums import CustomerDisplayMode, CustomerDisplaySectionCode
from backend.domain.customer_display.value_objects.display_section import DisplaySection
from backend.infrastructure.db.repositories.customer_display.base import CustomerDisplayRepositoryBase

_COLS = "id, mode, sections_json, active, created_at, updated_at"


class SqliteDisplayLayoutRepository(CustomerDisplayRepositoryBase):
    def save(self, layout: DisplayLayout) -> None:
        self._execute(
            f"INSERT INTO display_layouts ({_COLS})"
            " VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " sections_json=excluded.sections_json, active=excluded.active,"
            " updated_at=excluded.updated_at",
            self._params(layout),
        )

    def get(self, layout_id: str) -> DisplayLayout | None:
        row = self._query_one(f"SELECT {_COLS} FROM display_layouts WHERE id=?", (layout_id,))
        return self._hydrate(row) if row else None

    def list_by_mode(self, mode: CustomerDisplayMode) -> list[DisplayLayout]:
        rows = self._query(f"SELECT {_COLS} FROM display_layouts WHERE mode=?", (mode.value,))
        return [self._hydrate(row) for row in rows]

    def get_active_for_mode(self, mode: CustomerDisplayMode) -> DisplayLayout | None:
        row = self._query_one(
            f"SELECT {_COLS} FROM display_layouts WHERE mode=? AND active=1", (mode.value,),
        )
        return self._hydrate(row) if row else None

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(layout: DisplayLayout) -> tuple:
        return (
            layout.id, layout.mode.value, _serialize_sections(layout.sections), int(layout.active),
            layout.created_at, layout.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> DisplayLayout:
        return DisplayLayout(
            id=row["id"], mode=CustomerDisplayMode(row["mode"]), sections=_deserialize_sections(row["sections_json"]),
            active=bool(row["active"]), created_at=row["created_at"], updated_at=row["updated_at"],
        )


def _serialize_sections(sections: tuple[DisplaySection, ...]) -> str:
    return json.dumps([
        {"code": section.code.value, "order": section.order, "enabled": section.enabled}
        for section in sections
    ])


def _deserialize_sections(raw: str) -> tuple[DisplaySection, ...]:
    return tuple(
        DisplaySection(
            code=CustomerDisplaySectionCode(entry["code"]), order=entry["order"], enabled=entry["enabled"],
        )
        for entry in json.loads(raw or "[]")
    )
