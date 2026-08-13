"""CustomerTag use cases: create/deactivate the tag catalog, and assign/
remove a tag on a customer (§33-36). Tags carry no business-rule weight
("no sustituyen estatus/segmento/riesgo/consentimiento/territorio"), so
unlike segment membership there is no ``source`` to record.
"""

from __future__ import annotations

import json

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.result import CRMResult
from backend.domain.crm.entities.customer_tag import CustomerTag
from backend.domain.crm.entities.customer_tag_assignment import CustomerTagAssignment
from backend.domain.crm.events import CRMEvents, build_event_payload
from backend.domain.crm.exceptions import CRMDomainError
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


class _BaseUseCase:
    def __init__(self, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CRMAuthorizationPolicy()


class CreateCustomerTagUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, code: str, label: str,
                operation_id: str) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.TAGS_CREATE)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            if uow.tags.get_by_code(code):
                return CRMResult.fail("Ya existe una etiqueta con ese código", "DUPLICATE",
                                      operation_id=operation_id)
            try:
                tag = CustomerTag.create(code, label)
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.tags.save(tag)
            uow.audit.record(action=CRMEvents.TAG_CREATED, actor_user_id=actor_user_id,
                             operation_id=operation_id,
                             after_json=json.dumps({"tag_id": tag.id, "code": tag.code}))
            payload = build_event_payload(CRMEvents.TAG_CREATED, operation_id=operation_id,
                                          user_id=actor_user_id, tag_id=tag.id)
            uow.outbox.enqueue(payload["event_id"], CRMEvents.TAG_CREATED,
                               json.dumps(payload), operation_id)
            return CRMResult.ok("Etiqueta creada", entity_id=tag.id, operation_id=operation_id)


class DeactivateCustomerTagUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, tag_id: str,
                operation_id: str) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.TAGS_EDIT)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            tag = uow.tags.get(tag_id)
            if tag is None:
                return CRMResult.fail("La etiqueta no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            tag.deactivate()
            uow.tags.update(tag)
            uow.audit.record(action=CRMEvents.TAG_DEACTIVATED, actor_user_id=actor_user_id,
                             operation_id=operation_id,
                             after_json=json.dumps({"tag_id": tag.id}))
            payload = build_event_payload(CRMEvents.TAG_DEACTIVATED, operation_id=operation_id,
                                          user_id=actor_user_id, tag_id=tag.id)
            uow.outbox.enqueue(payload["event_id"], CRMEvents.TAG_DEACTIVATED,
                               json.dumps(payload), operation_id)
            return CRMResult.ok("Etiqueta desactivada", entity_id=tag.id,
                                operation_id=operation_id)


class AssignCustomerTagUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, customer_id: str, tag_id: str,
                operation_id: str) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.TAGS_ASSIGN)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            tag = uow.tags.get(tag_id)
            if tag is None:
                return CRMResult.fail("La etiqueta no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            if not tag.active:
                return CRMResult.fail("La etiqueta está inactiva", "VALIDATION",
                                      operation_id=operation_id)
            if uow.tag_assignments.get_active(customer_id, tag_id) is not None:
                return CRMResult.fail("El cliente ya tiene esta etiqueta", "DUPLICATE",
                                      operation_id=operation_id)
            try:
                assignment = CustomerTagAssignment.add(
                    customer_id, tag_id, assigned_by_user_id=actor_user_id,
                    operation_id=operation_id)
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.tag_assignments.save(assignment, operation_id=operation_id)
            uow.audit.record(
                action=CRMEvents.TAG_ASSIGNED, actor_user_id=actor_user_id,
                operation_id=operation_id,
                after_json=json.dumps({"customer_id": customer_id, "tag_id": tag_id}))
            payload = build_event_payload(
                CRMEvents.TAG_ASSIGNED, operation_id=operation_id, user_id=actor_user_id,
                customer_id=customer_id, tag_id=tag_id)
            uow.outbox.enqueue(payload["event_id"], CRMEvents.TAG_ASSIGNED,
                               json.dumps(payload), operation_id)
            return CRMResult.ok("Etiqueta asignada", entity_id=assignment.id,
                                operation_id=operation_id)


class RemoveCustomerTagUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, assignment_id: str,
                operation_id: str) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.TAGS_REMOVE)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            assignment = uow.tag_assignments.get(assignment_id)
            if assignment is None:
                return CRMResult.fail("La asignación de etiqueta no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            try:
                assignment.remove(removed_by_user_id=actor_user_id)
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.tag_assignments.update(assignment)
            uow.audit.record(
                action=CRMEvents.TAG_REMOVED, actor_user_id=actor_user_id,
                operation_id=operation_id,
                after_json=json.dumps({"customer_id": assignment.customer_id,
                                       "tag_id": assignment.tag_id}))
            payload = build_event_payload(
                CRMEvents.TAG_REMOVED, operation_id=operation_id, user_id=actor_user_id,
                customer_id=assignment.customer_id, tag_id=assignment.tag_id)
            uow.outbox.enqueue(payload["event_id"], CRMEvents.TAG_REMOVED,
                               json.dumps(payload), operation_id)
            return CRMResult.ok("Etiqueta removida", entity_id=assignment.id,
                                operation_id=operation_id)
