"""CRMNoteQueryService — read side for Notes. Reads only; never mutates.

Private notes (``is_private``) are filtered out of list results unless the
caller also holds ``NOTES_VIEW_PRIVATE`` — a masking-style permission
(CRM-2's ``FieldVisibility`` precedent), not a scope. A caller without
``NOTES_VIEW`` at all is denied outright, same as every other query
service in this bounded context.
"""

from __future__ import annotations

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.domain.crm.entities.crm_note import CRMNote
from backend.domain.crm.exceptions import CRMNoteNotFoundError
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


class CRMNoteQueryService:
    def __init__(self, connection, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._uow = CRMUnitOfWork(connection)
        self._auth = authorization or CRMAuthorizationPolicy()

    def get(self, note_id: str, *, actor_user_id: str) -> CRMNote:
        self._auth.require(actor_user_id, CRMPermissions.NOTES_VIEW)
        note = self._uow.notes.get(note_id)
        if note is None:
            raise CRMNoteNotFoundError(f"Nota {note_id!r} no existe")
        if note.is_private and not note.is_authored_by(actor_user_id):
            self._auth.require(actor_user_id, CRMPermissions.NOTES_VIEW_PRIVATE)
        return note

    def list_for_related_entity(self, related_entity_type: str, related_entity_id: str, *,
                                 actor_user_id: str) -> list[CRMNote]:
        self._auth.require(actor_user_id, CRMPermissions.NOTES_VIEW)
        notes = self._uow.notes.list_for_related_entity(related_entity_type, related_entity_id)
        can_view_private = self._auth.has_permission(actor_user_id,
                                                       CRMPermissions.NOTES_VIEW_PRIVATE)
        return [n for n in notes
                if not n.is_private or can_view_private or n.is_authored_by(actor_user_id)]
