"""CRMNote use cases: create, update, delete.

Update/delete are ownership-gated (NOTES_EDIT_OWN/NOTES_DELETE_OWN) — the
permission alone isn't enough, the caller must also be the note's own
author (see CRMNote.is_authored_by()). This is a hard invariant, not a
scope filter: a note author editing someone else's note is always denied,
regardless of any TEAM/COMPANY-style permission, because CRM-2's catalog
never defined one for notes (only OWN).
"""

from __future__ import annotations

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.result import CRMResult
from backend.domain.crm.entities.crm_note import CRMNote
from backend.domain.crm.enums import CRMRelatedEntityType
from backend.domain.crm.events import CRMEvents
from backend.domain.crm.exceptions import CRMDomainError
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


class CreateCRMNoteUseCase:
    def __init__(self, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CRMAuthorizationPolicy()

    def execute(
        self, connection, *, actor_user_id: str, related_entity_type: str,
        related_entity_id: str, body: str, operation_id: str, is_private: bool = False,
    ) -> CRMResult:
        permission = (CRMPermissions.NOTES_CREATE_PRIVATE if is_private
                      else CRMPermissions.NOTES_CREATE)
        try:
            self._auth.require(actor_user_id, permission)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        try:
            note = CRMNote.create(
                CRMRelatedEntityType(related_entity_type), related_entity_id, body,
                actor_user_id, is_private=is_private)
        except (CRMDomainError, ValueError) as exc:
            return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            uow.notes.save(note)
            uow.audit.record(action=CRMEvents.NOTE_CREATED, actor_user_id=actor_user_id,
                             note_id=note.id, reason="alta", operation_id=operation_id)
        return CRMResult.ok("Nota creada", entity_id=note.id, operation_id=operation_id)


class UpdateCRMNoteUseCase:
    def __init__(self, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CRMAuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, note_id: str, body: str,
                operation_id: str) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.NOTES_EDIT_OWN)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            note = uow.notes.get(note_id)
            if note is None:
                return CRMResult.fail("La nota no existe", "NOT_FOUND", operation_id=operation_id)
            if not note.is_authored_by(actor_user_id):
                return CRMResult.fail(
                    "Solo el autor puede editar esta nota", "PERMISSION_DENIED",
                    operation_id=operation_id)
            try:
                note.edit(body)
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.notes.update(note)
            uow.audit.record(action=CRMEvents.NOTE_UPDATED, actor_user_id=actor_user_id,
                             note_id=note.id, operation_id=operation_id)
        return CRMResult.ok("Nota actualizada", entity_id=note_id, operation_id=operation_id)


class DeleteCRMNoteUseCase:
    def __init__(self, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CRMAuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, note_id: str,
                operation_id: str) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.NOTES_DELETE_OWN)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            note = uow.notes.get(note_id)
            if note is None:
                return CRMResult.fail("La nota no existe", "NOT_FOUND", operation_id=operation_id)
            if not note.is_authored_by(actor_user_id):
                return CRMResult.fail(
                    "Solo el autor puede eliminar esta nota", "PERMISSION_DENIED",
                    operation_id=operation_id)
            uow.notes.delete(note_id)
            uow.audit.record(action=CRMEvents.NOTE_DELETED, actor_user_id=actor_user_id,
                             note_id=note_id, operation_id=operation_id)
        return CRMResult.ok("Nota eliminada", entity_id=note_id, operation_id=operation_id)
