"""SegmentationAdminQueryService (§33-36, CRM-43) — las bandejas de
segmentación: segmentos, etiquetas, territorios y carteras con sus miembros,
y los responsables vigentes por cliente.

Los servicios existentes leen POR CLIENTE (para el expediente); las pantallas
de administración necesitan la vista inversa (quiénes están en un segmento,
cuántos clientes tiene un territorio). Los conteos se calculan aquí, no en la
pantalla (§90).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


@dataclass(frozen=True)
class CatalogRow:
    entity: object
    member_count: int


@dataclass(frozen=True)
class MemberRow:
    link_id: str
    customer_id: str
    since: str
    by_user_id: str | None
    detail: str = ""


@dataclass(frozen=True)
class CustomerOwnersRow:
    customer_id: str
    owners: dict  # ownership_type -> CustomerOwnership vigente


class SegmentationAdminQueryService:
    def __init__(self, connection, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._uow = CRMUnitOfWork(connection)
        self._auth = authorization or CRMAuthorizationPolicy()

    # -- segmentos -------------------------------------------------------------
    def segments(self, *, actor_user_id: str) -> list[CatalogRow]:
        self._auth.require(actor_user_id, CRMPermissions.SEGMENTS_VIEW)
        return [CatalogRow(s, sum(1 for m in self._uow.segment_memberships.list_for_segment(s.id)
                                  if m.removed_at is None))
                for s in self._uow.segments.list_active()]

    def segment_members(self, segment_id: str, *, actor_user_id: str) -> list[MemberRow]:
        self._auth.require(actor_user_id, CRMPermissions.SEGMENTS_VIEW)
        return [MemberRow(m.id, m.customer_id, m.created_at, m.added_by_user_id,
                          m.source.value)
                for m in self._uow.segment_memberships.list_for_segment(segment_id)
                if m.removed_at is None]

    # -- etiquetas -------------------------------------------------------------
    def tags(self, *, actor_user_id: str) -> list[CatalogRow]:
        self._auth.require(actor_user_id, CRMPermissions.TAGS_VIEW)
        return [CatalogRow(t, sum(1 for a in self._uow.tag_assignments.list_for_tag(t.id)
                                  if a.removed_at is None))
                for t in self._uow.tags.list_active()]

    def tag_members(self, tag_id: str, *, actor_user_id: str) -> list[MemberRow]:
        self._auth.require(actor_user_id, CRMPermissions.TAGS_VIEW)
        return [MemberRow(a.id, a.customer_id, a.created_at, a.assigned_by_user_id)
                for a in self._uow.tag_assignments.list_for_tag(tag_id) if a.removed_at is None]

    # -- territorios -----------------------------------------------------------
    def territories(self, *, actor_user_id: str) -> list[CatalogRow]:
        self._auth.require(actor_user_id, CRMPermissions.TERRITORIES_VIEW)
        counts = self._uow.territories.customer_counts()
        return [CatalogRow(t, counts.get(t.id, 0)) for t in self._uow.territories.list_active()]

    def territory_members(self, territory_id: str, *, actor_user_id: str) -> list[MemberRow]:
        self._auth.require(actor_user_id, CRMPermissions.TERRITORIES_VIEW)
        return [MemberRow(r["id"], r["id"], r["updated_at"], None)
                for r in self._uow.territories.customers_in(territory_id)]

    # -- carteras --------------------------------------------------------------
    def portfolios(self, *, actor_user_id: str) -> list[CatalogRow]:
        self._auth.require(actor_user_id, CRMPermissions.PORTFOLIOS_VIEW)
        rows = []
        for portfolio in self._uow.portfolios.list_active():
            current = self._current_portfolio_members(portfolio.id)
            rows.append(CatalogRow(portfolio, len(current)))
        return rows

    def portfolio_members(self, portfolio_id: str, *, actor_user_id: str) -> list[MemberRow]:
        self._auth.require(actor_user_id, CRMPermissions.PORTFOLIOS_VIEW)
        return [MemberRow(a.id, a.customer_id, a.created_at, a.assigned_by_user_id, a.reason)
                for a in self._current_portfolio_members(portfolio_id)]

    def _current_portfolio_members(self, portfolio_id: str):
        """Una asignación es vigente si es la ÚLTIMA del cliente (historial
        append-only: reasignar crea otra fila)."""
        members = []
        for assignment in self._uow.portfolio_assignments.list_for_portfolio(portfolio_id):
            latest = self._uow.portfolio_assignments.get_latest(assignment.customer_id)
            if latest is not None and latest.id == assignment.id:
                members.append(assignment)
        return members

    # -- responsables ----------------------------------------------------------
    def owners(self, customer_ids, *, actor_user_id: str) -> list[CustomerOwnersRow]:
        self._auth.require(actor_user_id, CRMPermissions.CUSTOMER_OWNER_VIEW)
        rows = []
        for customer_id in customer_ids:
            current: dict = {}
            for ownership in self._uow.ownerships.list_for_customer(customer_id):
                current.setdefault(ownership.ownership_type.value, ownership)
            rows.append(CustomerOwnersRow(customer_id, current))
        return rows

    def owner_history(self, customer_id: str, *, actor_user_id: str):
        self._auth.require(actor_user_id, CRMPermissions.CUSTOMER_OWNER_VIEW)
        return self._uow.ownerships.list_for_customer(customer_id)
