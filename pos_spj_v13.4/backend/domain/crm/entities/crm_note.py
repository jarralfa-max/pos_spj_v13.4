"""CRMNote — a free-text note attached to a lead/opportunity/customer
(§23-26). Has no status lifecycle (it is not plannable/actionable like
CRMActivity/CRMTask, just text) — only edit/delete, and only by its own
author. Ownership is enforced at the application layer
(``NOTES_EDIT_OWN``/``NOTES_DELETE_OWN`` + an ``author_user_id`` match) —
the entity itself has no notion of "the current actor", same split as
every other permission check in this bounded context.

``is_private`` gates visibility via ``NOTES_VIEW_PRIVATE``/
``NOTES_CREATE_PRIVATE`` (a masking-style permission, not a scope) — see
CRM-2's ``FieldVisibility`` precedent for the general pattern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.crm.enums import CRMRelatedEntityType
from backend.domain.crm.exceptions import InvalidCRMNoteError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class CRMNote:
    id: str
    related_entity_type: CRMRelatedEntityType
    related_entity_id: str
    body: str
    author_user_id: str
    is_private: bool = False
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, related_entity_type: CRMRelatedEntityType, related_entity_id: str, body: str,
        author_user_id: str, *, is_private: bool = False,
    ) -> "CRMNote":
        if not related_entity_id:
            raise InvalidCRMNoteError("related_entity_id es obligatorio")
        if not body or not body.strip():
            raise InvalidCRMNoteError("body es obligatorio")
        if not author_user_id:
            raise InvalidCRMNoteError("author_user_id es obligatorio")
        return cls(
            id=new_uuid(), related_entity_type=related_entity_type,
            related_entity_id=related_entity_id, body=body.strip(),
            author_user_id=author_user_id, is_private=is_private,
        )

    def edit(self, body: str) -> None:
        if not body or not body.strip():
            raise InvalidCRMNoteError("body es obligatorio")
        self.body = body.strip()
        self.updated_at = _utcnow()

    def is_authored_by(self, user_id: str) -> bool:
        return self.author_user_id == user_id
