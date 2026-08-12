"""CRMNoteRepository — persists the CRMNote entity."""

from __future__ import annotations

from backend.domain.crm.entities.crm_note import CRMNote
from backend.domain.crm.enums import CRMRelatedEntityType
from backend.infrastructure.db.repositories.crm.base import CRMRepositoryBase

_NOTE_COLS = (
    "id, related_entity_type, related_entity_id, body, author_user_id,"
    " is_private, created_at, updated_at"
)


class CRMNoteRepository(CRMRepositoryBase):
    def save(self, note: CRMNote) -> None:
        self._execute(
            f"INSERT INTO crm_notes ({_NOTE_COLS}) VALUES (?,?,?,?,?,?,?,?)",
            (note.id, note.related_entity_type.value, note.related_entity_id, note.body,
             note.author_user_id, int(note.is_private), note.created_at, note.updated_at))

    def update(self, note: CRMNote) -> None:
        self._execute(
            "UPDATE crm_notes SET body=?, updated_at=? WHERE id=?",
            (note.body, note.updated_at, note.id))

    def delete(self, note_id: str) -> None:
        self._execute("DELETE FROM crm_notes WHERE id=?", (note_id,))

    def get(self, note_id: str) -> CRMNote | None:
        row = self._query_one(f"SELECT {_NOTE_COLS} FROM crm_notes WHERE id=?", (note_id,))
        return self._hydrate(row) if row else None

    def list_for_related_entity(self, related_entity_type: str,
                                 related_entity_id: str) -> list[CRMNote]:
        rows = self._query(
            f"SELECT {_NOTE_COLS} FROM crm_notes"
            " WHERE related_entity_type=? AND related_entity_id=? ORDER BY created_at DESC",
            (related_entity_type, related_entity_id))
        return [self._hydrate(r) for r in rows]

    @staticmethod
    def _hydrate(row: dict) -> CRMNote:
        return CRMNote(
            id=row["id"], related_entity_type=CRMRelatedEntityType(row["related_entity_type"]),
            related_entity_id=row["related_entity_id"], body=row["body"],
            author_user_id=row["author_user_id"], is_private=bool(row["is_private"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
