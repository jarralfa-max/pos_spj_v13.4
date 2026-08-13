"""CustomerSegment use cases: create/deactivate the segment catalog, and
add/remove a customer's membership (§33-36).

AddCustomerToSegmentUseCase accepts a ``source`` (MANUAL/RULE_BASED/
IMPORTED/ANALYTICS_GENERATED) — CRM never computes a RULE_BASED/
ANALYTICS_GENERATED membership itself ("BI puede sugerir, CRM administra
el uso operativo"): those sources are recorded here only when a BI/import
integration calls this use case, never derived internally.
"""

from __future__ import annotations

import json

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.result import CRMResult
from backend.domain.crm.entities.customer_segment import CustomerSegment
from backend.domain.crm.entities.customer_segment_membership import CustomerSegmentMembership
from backend.domain.crm.enums import SegmentMembershipSource
from backend.domain.crm.events import CRMEvents, build_event_payload
from backend.domain.crm.exceptions import CRMDomainError
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


class _BaseUseCase:
    def __init__(self, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CRMAuthorizationPolicy()


class CreateCustomerSegmentUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, code: str, name: str,
                operation_id: str, description: str = "",
                rule_definition: str = "") -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.SEGMENTS_CREATE)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            if uow.segments.get_by_code(code):
                return CRMResult.fail("Ya existe un segmento con ese código", "DUPLICATE",
                                      operation_id=operation_id)
            try:
                segment = CustomerSegment.create(code, name, description=description,
                                                 rule_definition=rule_definition)
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.segments.save(segment)
            uow.audit.record(action=CRMEvents.SEGMENT_CREATED, actor_user_id=actor_user_id,
                             operation_id=operation_id,
                             after_json=json.dumps({"segment_id": segment.id,
                                                    "code": segment.code}))
            payload = build_event_payload(CRMEvents.SEGMENT_CREATED, operation_id=operation_id,
                                          user_id=actor_user_id, segment_id=segment.id)
            uow.outbox.enqueue(payload["event_id"], CRMEvents.SEGMENT_CREATED,
                               json.dumps(payload), operation_id)
            return CRMResult.ok("Segmento creado", entity_id=segment.id,
                                operation_id=operation_id)


class DeactivateCustomerSegmentUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, segment_id: str,
                operation_id: str) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.SEGMENTS_EDIT)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            segment = uow.segments.get(segment_id)
            if segment is None:
                return CRMResult.fail("El segmento no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            segment.deactivate()
            uow.segments.update(segment)
            uow.audit.record(action=CRMEvents.SEGMENT_DEACTIVATED, actor_user_id=actor_user_id,
                             operation_id=operation_id,
                             after_json=json.dumps({"segment_id": segment.id}))
            payload = build_event_payload(CRMEvents.SEGMENT_DEACTIVATED,
                                          operation_id=operation_id, user_id=actor_user_id,
                                          segment_id=segment.id)
            uow.outbox.enqueue(payload["event_id"], CRMEvents.SEGMENT_DEACTIVATED,
                               json.dumps(payload), operation_id)
            return CRMResult.ok("Segmento desactivado", entity_id=segment.id,
                                operation_id=operation_id)


class AddCustomerToSegmentUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, customer_id: str, segment_id: str,
                operation_id: str,
                source: str = SegmentMembershipSource.MANUAL.value) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.SEGMENTS_ASSIGN)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        try:
            source_enum = SegmentMembershipSource(source)
        except ValueError:
            return CRMResult.fail(f"Fuente de membresía inválida: {source}", "VALIDATION",
                                  operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            segment = uow.segments.get(segment_id)
            if segment is None:
                return CRMResult.fail("El segmento no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            if not segment.active:
                return CRMResult.fail("El segmento está inactivo", "VALIDATION",
                                      operation_id=operation_id)
            if uow.segment_memberships.get_active(customer_id, segment_id) is not None:
                return CRMResult.fail("El cliente ya pertenece a este segmento", "DUPLICATE",
                                      operation_id=operation_id)
            try:
                membership = CustomerSegmentMembership.add(
                    customer_id, segment_id, source_enum, added_by_user_id=actor_user_id,
                    operation_id=operation_id)
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.segment_memberships.save(membership, operation_id=operation_id)
            uow.audit.record(
                action=CRMEvents.SEGMENT_MEMBER_ADDED, actor_user_id=actor_user_id,
                operation_id=operation_id,
                after_json=json.dumps({"customer_id": customer_id, "segment_id": segment_id,
                                       "source": source_enum.value}))
            payload = build_event_payload(
                CRMEvents.SEGMENT_MEMBER_ADDED, operation_id=operation_id,
                user_id=actor_user_id, customer_id=customer_id, segment_id=segment_id,
                source=source_enum.value)
            uow.outbox.enqueue(payload["event_id"], CRMEvents.SEGMENT_MEMBER_ADDED,
                               json.dumps(payload), operation_id)
            return CRMResult.ok("Cliente agregado al segmento", entity_id=membership.id,
                                operation_id=operation_id)


class RemoveCustomerFromSegmentUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, membership_id: str,
                operation_id: str) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.SEGMENTS_REMOVE)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            membership = uow.segment_memberships.get(membership_id)
            if membership is None:
                return CRMResult.fail("La membresía no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            try:
                membership.remove(removed_by_user_id=actor_user_id)
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.segment_memberships.update(membership)
            uow.audit.record(
                action=CRMEvents.SEGMENT_MEMBER_REMOVED, actor_user_id=actor_user_id,
                operation_id=operation_id,
                after_json=json.dumps({"customer_id": membership.customer_id,
                                       "segment_id": membership.segment_id}))
            payload = build_event_payload(
                CRMEvents.SEGMENT_MEMBER_REMOVED, operation_id=operation_id,
                user_id=actor_user_id, customer_id=membership.customer_id,
                segment_id=membership.segment_id)
            uow.outbox.enqueue(payload["event_id"], CRMEvents.SEGMENT_MEMBER_REMOVED,
                               json.dumps(payload), operation_id)
            return CRMResult.ok("Cliente removido del segmento", entity_id=membership.id,
                                operation_id=operation_id)
