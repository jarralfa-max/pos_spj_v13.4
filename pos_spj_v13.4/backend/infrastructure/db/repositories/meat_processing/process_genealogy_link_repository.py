"""ProcessGenealogyLinkRepository — persists ProcessGenealogyLink entities (§38).

Immutable edges (no ``save`` upsert path beyond insert-once — a link, once
recorded, is never rewritten, only ever added to). ``list_by_upstream``/
``list_by_downstream`` are the two primitives
``ProcessGenealogyQueryService`` (application layer) composes into
upstream/downstream/recall traversals.
"""

from __future__ import annotations

from backend.domain.meat_processing.entities.process_genealogy_link import ProcessGenealogyLink
from backend.infrastructure.db.repositories.meat_processing.base import (
    MeatProcessingRepositoryBase,
    dec_str,
    dt_str,
    parse_dt,
    to_decimal,
)


def _to_entity(row: dict) -> ProcessGenealogyLink:
    return ProcessGenealogyLink(
        id=row["id"], operation_id=row["operation_id"],
        upstream_entity_type=row["upstream_entity_type"],
        upstream_entity_id=row["upstream_entity_id"],
        downstream_entity_type=row["downstream_entity_type"],
        downstream_entity_id=row["downstream_entity_id"], product_id=row["product_id"],
        linked_by_user_id=row["linked_by_user_id"], lot_id=row["lot_id"],
        quantity=to_decimal(row["quantity"]), weight=to_decimal(row["weight"]),
        linked_at=parse_dt(row["linked_at"]))


class ProcessGenealogyLinkRepository(MeatProcessingRepositoryBase):
    def save(self, link: ProcessGenealogyLink) -> None:
        self._execute(
            "INSERT INTO process_genealogy_links (id, operation_id, upstream_entity_type,"
            " upstream_entity_id, downstream_entity_type, downstream_entity_id, product_id,"
            " lot_id, quantity, weight, linked_by_user_id, linked_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (link.id, link.operation_id, link.upstream_entity_type, link.upstream_entity_id,
             link.downstream_entity_type, link.downstream_entity_id, link.product_id,
             link.lot_id, dec_str(link.quantity), dec_str(link.weight),
             link.linked_by_user_id, dt_str(link.linked_at)))

    def get(self, link_id: str) -> ProcessGenealogyLink | None:
        row = self._query_one("SELECT * FROM process_genealogy_links WHERE id=?", (link_id,))
        return None if row is None else _to_entity(row)

    def list_by_upstream(self, entity_type: str, entity_id: str) -> list[ProcessGenealogyLink]:
        rows = self._query(
            "SELECT * FROM process_genealogy_links WHERE upstream_entity_type=?"
            " AND upstream_entity_id=? ORDER BY linked_at", (entity_type, entity_id))
        return [_to_entity(row) for row in rows]

    def list_by_downstream(self, entity_type: str, entity_id: str) -> list[ProcessGenealogyLink]:
        rows = self._query(
            "SELECT * FROM process_genealogy_links WHERE downstream_entity_type=?"
            " AND downstream_entity_id=? ORDER BY linked_at", (entity_type, entity_id))
        return [_to_entity(row) for row in rows]

    def list_by_lot(self, lot_id: str) -> list[ProcessGenealogyLink]:
        rows = self._query(
            "SELECT * FROM process_genealogy_links WHERE lot_id=? ORDER BY linked_at",
            (lot_id,))
        return [_to_entity(row) for row in rows]
