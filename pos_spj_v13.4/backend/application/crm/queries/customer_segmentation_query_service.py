"""CustomerSegmentationQueryService — read side for CustomerSegment/
CustomerTag and their per-customer memberships/assignments. Reads only;
never mutates.

§57's minimum query-service list names CustomerPortfolioQueryService and
CustomerOwnershipQueryService individually but does not split segments and
tags into two separate services — this consolidates both under one service,
same "no dedicated service beyond what the master prompt actually names"
judgment CRM-9 made consolidating consent+preference queries. Territory is
deliberately excluded: ``Customer.territory_id`` is a plain field already
reachable through the Customers bounded context's own profile query
service, not something this CRM-side service needs to re-expose. Flat
SEGMENTS_VIEW/TAGS_VIEW permissions, same no-scope-suffix precedent as
CRMActivityQueryService.
"""

from __future__ import annotations

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.domain.crm.entities.customer_segment import CustomerSegment
from backend.domain.crm.entities.customer_segment_membership import CustomerSegmentMembership
from backend.domain.crm.entities.customer_tag import CustomerTag
from backend.domain.crm.entities.customer_tag_assignment import CustomerTagAssignment
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


class CustomerSegmentationQueryService:
    def __init__(self, connection, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._uow = CRMUnitOfWork(connection)
        self._auth = authorization or CRMAuthorizationPolicy()

    def list_active_segments(self, *, actor_user_id: str) -> list[CustomerSegment]:
        self._auth.require(actor_user_id, CRMPermissions.SEGMENTS_VIEW)
        return self._uow.segments.list_active()

    def list_active_memberships(self, customer_id: str, *,
                                actor_user_id: str) -> list[CustomerSegmentMembership]:
        self._auth.require(actor_user_id, CRMPermissions.SEGMENTS_VIEW)
        return self._uow.segment_memberships.list_active_for_customer(customer_id)

    def list_segment_members(self, segment_id: str, *,
                             actor_user_id: str) -> list[CustomerSegmentMembership]:
        self._auth.require(actor_user_id, CRMPermissions.SEGMENTS_VIEW)
        return [m for m in self._uow.segment_memberships.list_for_segment(segment_id)
                if m.is_active()]

    def list_active_tags(self, *, actor_user_id: str) -> list[CustomerTag]:
        self._auth.require(actor_user_id, CRMPermissions.TAGS_VIEW)
        return self._uow.tags.list_active()

    def list_active_tag_assignments(self, customer_id: str, *,
                                    actor_user_id: str) -> list[CustomerTagAssignment]:
        self._auth.require(actor_user_id, CRMPermissions.TAGS_VIEW)
        return self._uow.tag_assignments.list_active_for_customer(customer_id)
